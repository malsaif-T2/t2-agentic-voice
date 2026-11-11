"""ECAPA on VoxLingua107 behind the `LanguageClassifier` port (plan 007's Block H, Q15):
SpeechBrain's `EncoderClassifier` on torch, on the CPU, through the library's `ecapa` extra.

**torch only here, only when asked.** The base install holds no torch (the torch check), so this
module imports neither torch nor SpeechBrain: `load` loads them, through
`importlib.import_module` with literal names (which ARCH-OWNER and ARCH-BAN read), and without
the extra it is a ConfigurationError naming the group that installs it. mypy reads torch through
`_Torch`, so `poe types` gives one answer with or without it.

**The files** (adapters/model_files.py): the model's six files, from the Hugging Face
repository `speechbrain/lang-id-voxlingua107-ecapa` at commit
`0253049ae131d6a4be1c4f0d8b0ff483a0f8c8e9` (Apache-2.0), pinned by size and SHA-256
(`ECAPA_FILES`), in the folder `stt.classifier_dir` names. SpeechBrain puts that folder on
`sys.path`, so `load` refuses one that holds a `.py` file. It loads by exactly
`from_hparams(source=folder, savedir=folder, overrides={"pretrained_path": folder},
local_strategy=LocalStrategy.NO_LINK, run_opts={"device": "cpu"})`, which reaches no host and
writes nothing into the folder, then checks that the label encoder gives Arabic and English
their pinned outputs, 3 and 20 (`ECAPA_LABELS`), and sets torch's threads to
`stt.classifier_threads`.

**A classification.** The caller's PCM16 as float32 samples to `classify_batch`, whose
log-probabilities are exponentiated and each code asked divided by their sum, the answer's
`mass` (`LanguageScores.renormalized`), on a worker thread, one classification at a time a
process (a second is busy: None).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from threading import Lock
from typing import Any, Final, Protocol, Self, cast

import numpy as np

from t2_agentic_voice.adapters.model_files import (
    GUIDE,
    ONE_AT_A_TIME,
    ModelFile,
    Samples,
    checked,
    heard_codes,
    samples,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

ECAPA_FILES: Final = (
    ModelFile(
        name="embedding_model.ckpt",
        size=84_474_355,
        sha256="ab750d5c06d713477045fa798fab5d33e959dbc0dfe4de510a9a47844c79a19a",
    ),
    ModelFile(
        name="classifier.ckpt",
        size=762_555,
        sha256="a50d9024ff58d317031c9787d4c6c614d454a87a8ef32f9d36338cd3ff57adbc",
    ),
    ModelFile(
        name="normalizer.ckpt",
        size=1_063,
        sha256="c369e01dfa2e0d84c6b116f33c7b94f1fe28c061642086538e93cde3d97c26ef",
    ),
    ModelFile(
        name="hyperparams.yaml",
        size=1_519,
        sha256="88fec9791a8416a152fb10834327e18d38e5bf7a351e9b714e08cdc4af05de6f",
    ),
    ModelFile(
        name="label_encoder.txt",
        size=2_204,
        sha256="9f566d83c4f19168be4a0bf86c0c7dac7d3264a95105bcbf33a7c32b83ccc17f",
    ),
    ModelFile(
        name="config.json",
        size=51,
        sha256="a861f8fbc2e23c0fc0823b3c0fd2b3d1e839563c2d4e3f9663a1237cce62bc89",
    ),
)
# Each code the library speaks, with the label encoder's label and its output.
ECAPA_LABELS: Final = {"ar": ("ar: Arabic", 3), "en": ("en: English", 20)}
EXTRA_FIX: Final = (
    "FIX: install the library's ecapa extra (t2-agentic-voice[ecapa]; in this workspace: uv sync "
    f"--group language-id), or set stt.classifier to silero ({GUIDE})."
)

# The model: its input samples to its 107 log-probabilities.
type Runner = Callable[[Samples], Samples]
_LOADED: dict[tuple[Path, int], Runner] = {}
_LOADING = Lock()


class _Torch(Protocol):
    """What the adapter reads of torch, so mypy never reads torch itself."""

    def set_num_threads(self, threads: int, /) -> None: ...

    def from_numpy(self, array: Samples, /) -> Any: ...

    def no_grad(self) -> AbstractContextManager[object]: ...


def _libraries() -> tuple[_Torch, Any, Any]:
    """torch, SpeechBrain's classifiers and its fetching module, loaded now; a
    ConfigurationError naming the extra when they are not installed."""
    try:
        torch = importlib.import_module("torch")
        classifiers = importlib.import_module("speechbrain.inference.classifiers")
        fetching = importlib.import_module("speechbrain.utils.fetching")
    except ImportError:
        raise ConfigurationError(
            "stt.classifier ecapa runs on torch and SpeechBrain, which the library's base "
            f"install does not hold. {EXTRA_FIX}"
        ) from None
    return cast(_Torch, torch), classifiers, fetching


class EcapaLanguage:
    """ECAPA's spoken-language classifier (the module's docstring), on the model files in
    `folder` (`stt.classifier_dir`), each checked against its pins, on `threads` threads; a
    test gives its pins (`_files`) or its model (`_runner`)."""

    name = "ecapa"

    def __init__(
        self,
        folder: Path | None,
        *,
        threads: int,
        _files: Sequence[ModelFile] = ECAPA_FILES,
        _runner: Runner | None = None,
    ) -> None:
        self.folder, self.threads, self._files = folder, threads, tuple(_files)
        self._runner = _runner

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> Self:
        """Built from the `stt` group, with no IO: its files are checked at `load`."""
        stt = settings.stt
        return cls(stt.classifier_dir, threads=stt.classifier_threads)

    async def load(self, among: Sequence[str]) -> None:
        """Check the codes and the files, then load torch, SpeechBrain and the model, off the
        event loop, once a process (the port's `load`)."""
        heard_codes(self.name, among, list(ECAPA_LABELS))
        if self._runner is None:
            self._runner = await asyncio.to_thread(self._open)

    def _open(self) -> Runner:
        folder = checked(self.folder, self._files)
        code = sorted(path.name for path in folder.iterdir() if path.suffix == ".py")
        if code:
            raise ConfigurationError(
                f"stt.classifier_dir holds {', '.join(code)}, and SpeechBrain puts the folder on "
                f"sys.path. FIX: keep only the pinned model files there ({GUIDE})."
            )
        key = (folder.resolve(), self.threads)
        with _LOADING:
            if key not in _LOADED:
                _LOADED[key] = _model(folder, self.threads)
            return _LOADED[key]

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        """The share of each code of `among` in `clip` (the port's `classify`)."""
        runner = self._runner
        if runner is None or any(code not in ECAPA_LABELS for code in among):
            raise ProviderError("server_error", False)
        given = samples(clip)
        return await asyncio.to_thread(_classified, runner, given, tuple(among))

    async def aclose(self) -> None:
        """Let the model go from this classifier (the process keeps its one load)."""
        self._runner = None


def _model(folder: Path, threads: int) -> Runner:
    """The model of the files in `folder`, loaded as the module's docstring says."""
    torch, classifiers, fetching = _libraries()
    source = str(folder)
    model = classifiers.EncoderClassifier.from_hparams(
        source=source,
        savedir=source,
        overrides={"pretrained_path": source},
        local_strategy=fetching.LocalStrategy.NO_LINK,
        run_opts={"device": "cpu"},
    )
    found = model.hparams.label_encoder.lab2ind
    for label, index in ECAPA_LABELS.values():
        if found.get(label) != index:
            raise ConfigurationError(
                f"The model's label encoder does not give {label} the output {index}. FIX: "
                f"fetch the pinned files again as {GUIDE} says."
            )
    torch.set_num_threads(threads)

    def run(given: Samples) -> Samples:
        with torch.no_grad():
            log_probs = model.classify_batch(torch.from_numpy(given).unsqueeze(0))[0][0]
        return np.asarray(log_probs, dtype=np.float32)

    return run


def _classified(runner: Runner, given: Samples, among: tuple[str, ...]) -> LanguageScores | None:
    """On a worker thread: the model's probabilities of the codes `among`; None while another
    classification runs."""
    if not ONE_AT_A_TIME.acquire(blocking=False):
        return None
    try:
        log_probs = np.asarray(runner(given), dtype=np.float64)
    finally:
        ONE_AT_A_TIME.release()
    found = {code: float(np.exp(log_probs[ECAPA_LABELS[code][1]])) for code in among}
    return LanguageScores.renormalized(found, among=among)
