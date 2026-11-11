"""ECAPA on VoxLingua107 behind the `LanguageClassifier` port (adapters/ecapa_language.py; plan
007's Block H, Q15), with an injected runner or stand-in torch and SpeechBrain modules, so no
model and no torch: its label map (index 3 Arabic, 20 English, checked against the model's label
encoder), its log-probabilities exponentiated and renormalized over the codes asked, the
caller's PCM16 as float32, the thread count; the module imports alone in a new process without
torch; `load` without the extra names the group to install; the load call is given the folder
as its source, its save folder and its `pretrained_path`, with `NO_LINK` on the CPU; and a folder
holding a `.py` file, which SpeechBrain would put on `sys.path`, is refused."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from t2_agentic_voice.adapters.ecapa_language import ECAPA_FILES, ECAPA_LABELS, EcapaLanguage
from t2_agentic_voice.adapters.model_files import ModelFile
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[3]
AMONG = ("ar", "en")
Samples = npt.NDArray[np.float32]


def _log_probs() -> Samples:
    """107 log-probabilities: Arabic 0.6, English 0.2, the rest sharing 0.2."""
    probabilities = np.full(107, 0.2 / 105, dtype=np.float64)
    probabilities[3], probabilities[20] = 0.6, 0.2
    return np.log(probabilities).astype(np.float32)


def _clip(*samples: int) -> AudioClip:
    return AudioClip(pcm16=np.array(samples, dtype="<i2").tobytes(), sample_rate=16_000)


def test_the_label_map_and_the_pins_are_the_approved_ones() -> None:
    assert ECAPA_LABELS == {"ar": ("ar: Arabic", 3), "en": ("en: English", 20)}
    pinned = {file.name: (file.size, file.sha256) for file in ECAPA_FILES}
    assert set(pinned) == {
        "embedding_model.ckpt",
        "classifier.ckpt",
        "normalizer.ckpt",
        "hyperparams.yaml",
        "label_encoder.txt",
        "config.json",
    }
    assert pinned["embedding_model.ckpt"] == (
        84_474_355,
        "ab750d5c06d713477045fa798fab5d33e959dbc0dfe4de510a9a47844c79a19a",
    )
    assert pinned["classifier.ckpt"][0] == 762_555 and pinned["normalizer.ckpt"][0] == 1_063
    assert sum(size for size, _ in pinned.values()) == 85_241_747


def test_its_log_probabilities_are_exponentiated_and_renormalized_with_their_mass() -> None:
    inputs: list[Samples] = []

    def runner(samples: Samples) -> Samples:
        inputs.append(samples)
        return _log_probs()

    ecapa = EcapaLanguage(None, threads=2, _runner=runner)
    asyncio.run(ecapa.load(AMONG))
    scores = asyncio.run(ecapa.classify(_clip(0, 16_384, -32_768), among=AMONG))
    assert scores is not None
    assert scores.shares == pytest.approx({"ar": 0.75, "en": 0.25}, abs=1e-5)
    assert scores.mass == pytest.approx(0.8, abs=1e-5)
    (samples,) = inputs
    assert samples.dtype == np.float32 and samples.tolist() == [0.0, 0.5, -1.0]


def test_the_module_imports_alone_in_a_new_process_without_torch() -> None:
    """torch and SpeechBrain refused in the child: the module still imports, and loads
    neither."""
    child = (
        "import sys\n"
        "for name in ('torch', 'torchaudio', 'speechbrain', 'huggingface_hub'):\n"
        "    sys.modules[name] = None\n"
        "import t2_agentic_voice.adapters.ecapa_language\n"
        "import t2_agentic_voice.adapters.silero_language\n"
        "assert 'onnxruntime' not in sys.modules\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", child],
        cwd=ROOT,
        env=child_shell(),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert (done.returncode, done.stderr) == (0, b""), done.stderr.decode(errors="replace")


def test_load_without_the_extra_names_the_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    ecapa = EcapaLanguage(tmp_path, threads=2, _files=_files(tmp_path))
    with pytest.raises(ConfigurationError) as refused:
        asyncio.run(ecapa.load(AMONG))
    assert "uv sync --group language-id" in refused.value.message
    assert "ecapa" in refused.value.message


def _files(folder: Path) -> tuple[ModelFile, ...]:
    data = b"hyperparams stand-in"
    (folder / "hyperparams.yaml").write_bytes(data)
    pin = ModelFile(
        name="hyperparams.yaml", size=len(data), sha256=hashlib.sha256(data).hexdigest()
    )
    return (pin,)


class _Model:
    """What `EncoderClassifier.from_hparams` returns, as far as the adapter reads it."""

    def __init__(self, labels: dict[str, int]) -> None:
        self.hparams = SimpleNamespace(label_encoder=SimpleNamespace(lab2ind=labels))
        self.batches: list[Any] = []

    def classify_batch(self, wavs: Any) -> tuple[Any, ...]:
        self.batches.append(wavs)
        return (_log_probs()[None, :], None, None, None)


def _stand_ins(monkeypatch: pytest.MonkeyPatch, labels: dict[str, int]) -> dict[str, Any]:
    """torch and SpeechBrain stand-ins in `sys.modules`: what each was asked."""
    asked: dict[str, Any] = {"threads": [], "loads": []}
    model = _Model(labels)
    asked["model"] = model

    def from_hparams(**given: Any) -> _Model:
        asked["loads"].append(given)
        return model

    torch = ModuleType("torch")
    torch.set_num_threads = asked["threads"].append  # type: ignore[attr-defined]
    torch.no_grad = contextlib.nullcontext  # type: ignore[attr-defined]
    torch.from_numpy = lambda array: SimpleNamespace(unsqueeze=lambda dim: array[None, :])  # type: ignore[attr-defined]
    classifiers = ModuleType("speechbrain.inference.classifiers")
    classifiers.EncoderClassifier = SimpleNamespace(from_hparams=from_hparams)  # type: ignore[attr-defined]
    fetching = ModuleType("speechbrain.utils.fetching")
    fetching.LocalStrategy = SimpleNamespace(NO_LINK="no-link", COPY="copy")  # type: ignore[attr-defined]
    for name, module in {
        "torch": torch,
        "speechbrain": ModuleType("speechbrain"),
        "speechbrain.inference": ModuleType("speechbrain.inference"),
        "speechbrain.inference.classifiers": classifiers,
        "speechbrain.utils": ModuleType("speechbrain.utils"),
        "speechbrain.utils.fetching": fetching,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return asked


def test_the_load_call_is_given_the_folder_no_link_and_the_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _stand_ins(monkeypatch, {"ar: Arabic": 3, "en: English": 20})
    ecapa = EcapaLanguage(tmp_path, threads=3, _files=_files(tmp_path))
    asyncio.run(ecapa.load(AMONG))
    folder = str(tmp_path)
    assert asked["loads"] == [
        {
            "source": folder,
            "savedir": folder,
            "overrides": {"pretrained_path": folder},
            "local_strategy": "no-link",
            "run_opts": {"device": "cpu"},
        }
    ]
    assert asked["threads"] == [3]
    scores = asyncio.run(ecapa.classify(_clip(1, 2, 3), among=AMONG))
    assert scores is not None and math.isclose(scores.shares["ar"], 0.75, abs_tol=1e-5)
    (batch,) = asked["model"].batches
    assert batch.shape == (1, 3) and batch.dtype == np.float32


def test_a_model_whose_labels_disagree_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stand_ins(monkeypatch, {"ar: Arabic": 20, "en: English": 3})
    ecapa = EcapaLanguage(tmp_path, threads=2, _files=_files(tmp_path))
    with pytest.raises(ConfigurationError, match="label"):
        asyncio.run(ecapa.load(AMONG))


def test_a_folder_holding_a_python_file_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _stand_ins(monkeypatch, {"ar: Arabic": 3, "en: English": 20})
    (tmp_path / "custom.py").write_text("", encoding="utf-8")
    ecapa = EcapaLanguage(tmp_path, threads=2, _files=_files(tmp_path))
    with pytest.raises(ConfigurationError, match=r"custom\.py.*FIX"):
        asyncio.run(ecapa.load(AMONG))
    assert asked["loads"] == []  # refused before SpeechBrain is asked


def test_a_code_it_cannot_hear_is_refused_before_any_call() -> None:
    ecapa = EcapaLanguage(None, threads=2, _runner=lambda samples: _log_probs())
    with pytest.raises(ConfigurationError, match="FIX"):
        asyncio.run(ecapa.load(("ar", "fr")))
