"""Silero's 95-language spoken-language classifier behind the `LanguageClassifier` port (plan 007's
Block H): `lang_classifier_95.onnx` on onnxruntime, on the CPU, with no torch.

**The files** (adapters/model_files.py): the model and its label map, from the Hugging Face
repository `deepghs/silero-lang95-onnx` at commit `bf21c4f59503dc182ab4d69328889b93c51bf70f`, a
third party's re-upload of the file silero-vad v4.0 loads (MIT, Silero Team), pinned by size and
SHA-256 (`SILERO_FILES`), in the folder `stt.classifier_dir` names. `load` checks each, and that
the label map gives Arabic and English the model's outputs 55 and 30 (`SILERO_LABELS`).

**A classification.** The caller's PCM16 as float32 samples, the model's 95 language logits, a
softmax, then each code asked divided by their sum, which is the answer's `mass`
(`LanguageScores.renormalized`), all on a worker thread with `stt.classifier_threads` intra-op
threads, one classification at a time a process (a second is busy: None). The model is loaded
once a process, off the event loop; importing onnxruntime takes seconds, so it is imported only
then.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Lock
from typing import Final, Self

import numpy as np

from t2_agentic_voice.adapters.model_files import (
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

MODEL: Final = "lang_classifier_95.onnx"
LABELS: Final = "lang_dict_95.json"
SILERO_FILES: Final = (
    ModelFile(
        name=MODEL,
        size=16_972_591,
        sha256="12a91f706ad6ca5a5eba4e84a96739d077e56f121ec71db86a752f62e218a227",
    ),
    ModelFile(
        name=LABELS,
        size=2_183,
        sha256="70b62ef4939d712b960a8ed8aaea9e0d7117b10877e917a97cc4e8bbb7bd340f",
    ),
)
# Each code the library speaks, with the model's output that is its language.
SILERO_LABELS: Final = {"ar": 55, "en": 30}

# The model: its input samples to its 95 language logits.
type Runner = Callable[[Samples], Samples]
# What opens the model of a file with a count of threads.
type Opener = Callable[[Path, int], Runner]
_LOADED: dict[tuple[object, Path, int], Runner] = {}
_LOADING = Lock()


def _session(path: Path, threads: int) -> Runner:
    """An onnxruntime session of the model on the CPU with `threads` intra-op threads."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.log_severity_level = 3  # errors only: the model warns of its output shapes each run
    session = onnxruntime.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )
    name = session.get_inputs()[0].name

    def run(given: Samples) -> Samples:
        logits = session.run(None, {name: given[None, :]})[0][0]
        return np.asarray(logits, dtype=np.float32)

    return run


class SileroLanguage:
    """Silero's spoken-language classifier (the module's docstring), on the model files in
    `folder` (`stt.classifier_dir`), each checked against its pins, its model run on `threads`
    threads; a test gives its pins (`_files`), its model (`_runner`), or what opens one
    (`_opener`)."""

    name = "silero"

    def __init__(
        self,
        folder: Path | None,
        *,
        threads: int,
        _files: Sequence[ModelFile] = SILERO_FILES,
        _runner: Runner | None = None,
        _opener: Opener | None = None,
    ) -> None:
        self.folder, self.threads, self._files = folder, threads, tuple(_files)
        self._runner, self._opener = _runner, _opener

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> Self:
        """Built from the `stt` group, with no IO: its files are checked at `load`."""
        stt = settings.stt
        return cls(stt.classifier_dir, threads=stt.classifier_threads)

    async def load(self, among: Sequence[str]) -> None:
        """Check the codes, the files and the label map, then load the model, off the event
        loop, once a process (the port's `load`)."""
        heard_codes(self.name, among, list(SILERO_LABELS))
        if self._runner is None:
            self._runner = await asyncio.to_thread(self._open)

    def _open(self) -> Runner:
        folder = checked(self.folder, self._files)
        _check_labels(folder / LABELS)
        opener: Opener = self._opener or _session
        key = (opener, folder.resolve(), self.threads)
        with _LOADING:
            if key not in _LOADED:
                _LOADED[key] = opener(folder / MODEL, self.threads)
            return _LOADED[key]

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        """The share of each code of `among` in `clip` (the port's `classify`)."""
        runner = self._runner
        if runner is None or any(code not in SILERO_LABELS for code in among):
            raise ProviderError("server_error", False)
        given = samples(clip)
        return await asyncio.to_thread(_classified, runner, given, tuple(among))

    async def aclose(self) -> None:
        """Let the model go from this classifier (the process keeps its one load)."""
        self._runner = None


def _classified(runner: Runner, given: Samples, among: tuple[str, ...]) -> LanguageScores | None:
    """On a worker thread: the model's softmax over the codes `among`; None while another
    classification runs."""
    if not ONE_AT_A_TIME.acquire(blocking=False):
        return None
    try:
        logits = np.asarray(runner(given), dtype=np.float64)
    finally:
        ONE_AT_A_TIME.release()
    exp = np.exp(logits - logits.max())
    probabilities = exp / exp.sum()
    found = {code: float(probabilities[SILERO_LABELS[code]]) for code in among}
    return LanguageScores.renormalized(found, among=among)


def _check_labels(path: Path) -> None:
    """The label map gives each code its pinned output; a ConfigurationError otherwise."""
    try:
        labels = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        labels = None
    named = {} if not isinstance(labels, dict) else labels
    for code, index in SILERO_LABELS.items():
        entry = named.get(str(index))
        if not isinstance(entry, str) or entry.split(",")[0].strip() != code:
            raise ConfigurationError(
                f"The label map {LABELS} in stt.classifier_dir does not give {code} the "
                f"model's output {index}. FIX: fetch the pinned files again as "
                "docs/guide/languages.md says."
            )
