"""Silero's spoken-language classifier behind the `LanguageClassifier` port (adapters/
silero_language.py; plan 007's Block H), with an injected runner and opener, so no model file
and no onnxruntime session: its label map (code 55 Arabic, 30 English, checked against the
pinned label file at load), the softmax renormalized over the codes asked with its mass, the
caller's PCM16 as float32, the session's thread count, the model loaded once a process, one
classification at a time (a second while one runs is busy), and the ConfigurationErrors before
any call: a code it cannot hear, no folder, a label file that disagrees."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import threading
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest
from t2_agentic_voice.adapters.model_files import ModelFile
from t2_agentic_voice.adapters.silero_language import (
    SILERO_FILES,
    SILERO_LABELS,
    SileroLanguage,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

AMONG = ("ar", "en")
Samples = npt.NDArray[np.float32]


class Runner:
    """A model of 95 outputs: Arabic's logit 2, English's 1, the rest 0; it keeps each input."""

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.inputs: list[Samples] = []
        self.gate = gate

    def __call__(self, samples: Samples) -> Samples:
        self.inputs.append(samples)
        if self.gate is not None:
            self.gate.wait(5)
        logits = np.zeros(95, dtype=np.float32)
        logits[55], logits[30] = 2.0, 1.0
        return logits


def _clip(*samples: int) -> AudioClip:
    return AudioClip(pcm16=np.array(samples, dtype="<i2").tobytes(), sample_rate=16_000)


def _files(folder: Path, labels: dict[str, str] | None = None) -> tuple[ModelFile, ...]:
    """Small stand-ins for the pinned files, pinned to what the test wrote."""
    given = labels or {"55": "ar, Arabic", "30": "en, English", "0": "ru, Russian"}
    content = {
        "lang_classifier_95.onnx": b"not a model",
        "lang_dict_95.json": json.dumps(given).encode(),
    }
    files = []
    for name, data in content.items():
        (folder / name).write_bytes(data)
        files.append(ModelFile(name=name, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return tuple(files)


def test_the_label_map_and_the_pins_are_the_approved_ones() -> None:
    assert SILERO_LABELS == {"ar": 55, "en": 30}
    names = [file.name for file in SILERO_FILES]
    assert names == ["lang_classifier_95.onnx", "lang_dict_95.json"]
    onnx = SILERO_FILES[0]
    assert (onnx.size, onnx.sha256) == (
        16_972_591,
        "12a91f706ad6ca5a5eba4e84a96739d077e56f121ec71db86a752f62e218a227",
    )


def test_the_softmax_is_renormalized_over_the_codes_asked_with_its_mass() -> None:
    runner = Runner()
    silero = SileroLanguage(None, threads=2, _runner=runner)
    asyncio.run(silero.load(AMONG))
    scores = asyncio.run(silero.classify(_clip(0, 100, -100), among=AMONG))
    assert scores is not None
    e2, e1 = math.exp(2), math.exp(1)
    assert scores.shares == pytest.approx({"ar": e2 / (e2 + e1), "en": e1 / (e2 + e1)})
    assert scores.mass == pytest.approx((e2 + e1) / (e2 + e1 + 93))
    assert scores.best[0] == "ar"


def test_the_callers_pcm16_reaches_the_model_as_float32() -> None:
    runner = Runner()
    silero = SileroLanguage(None, threads=2, _runner=runner)
    asyncio.run(silero.classify(_clip(0, 16_384, -32_768, 32_767), among=AMONG))
    (samples,) = runner.inputs
    assert samples.dtype == np.float32
    assert samples.tolist() == pytest.approx([0.0, 0.5, -1.0, 32_767 / 32_768])


def test_load_checks_the_files_and_the_labels_then_opens_the_model_with_its_threads(
    tmp_path: Path,
) -> None:
    opened: list[tuple[Path, int]] = []

    def opener(path: Path, threads: int) -> Runner:
        opened.append((path, threads))
        return Runner()

    files = _files(tmp_path)
    first = SileroLanguage(tmp_path, threads=3, _files=files, _opener=opener)
    second = SileroLanguage(tmp_path, threads=3, _files=files, _opener=opener)
    asyncio.run(first.load(AMONG))
    asyncio.run(second.load(AMONG))
    assert opened == [(tmp_path / "lang_classifier_95.onnx", 3)]  # once a process
    assert asyncio.run(second.classify(_clip(1, 2), among=AMONG)) is not None


def test_a_label_file_that_disagrees_with_the_map_is_refused(tmp_path: Path) -> None:
    files = _files(tmp_path, {"55": "en, English", "30": "ar, Arabic"})
    silero = SileroLanguage(tmp_path, threads=2, _files=files, _opener=lambda p, t: Runner())
    with pytest.raises(ConfigurationError, match=r"lang_dict_95\.json.*FIX"):
        asyncio.run(silero.load(AMONG))


@pytest.mark.parametrize("among", [("ar", "fr"), ("xx",), ()])
def test_a_code_it_cannot_hear_is_refused_before_any_call(among: Sequence[str]) -> None:
    silero = SileroLanguage(None, threads=2, _runner=Runner())
    with pytest.raises(ConfigurationError, match="FIX"):
        asyncio.run(silero.load(among))


def test_no_folder_is_refused_at_load_with_the_setting() -> None:
    silero = SileroLanguage(None, threads=2, _opener=lambda p, t: Runner())
    with pytest.raises(ConfigurationError, match=r"stt\.classifier_dir is not set"):
        asyncio.run(silero.load(AMONG))


def test_a_classification_while_one_runs_is_busy_and_one_before_load_fails() -> None:
    gate = threading.Event()
    silero = SileroLanguage(None, threads=2, _runner=Runner(gate))

    async def both() -> list[object]:
        first = asyncio.create_task(silero.classify(_clip(1), among=AMONG))
        await asyncio.sleep(0.2)
        second = await silero.classify(_clip(2), among=AMONG)
        gate.set()
        return [await first, second]

    first, second = asyncio.run(both())
    assert first is not None and second is None
    with pytest.raises(ProviderError):
        asyncio.run(SileroLanguage(None, threads=2).classify(_clip(1), among=AMONG))


def test_a_clip_at_another_rate_is_refused() -> None:
    silero = SileroLanguage(None, threads=2, _runner=Runner())
    clip = AudioClip(pcm16=b"\x00\x00" * 8, sample_rate=8_000)
    with pytest.raises(ProviderError) as refused:
        asyncio.run(silero.classify(clip, among=AMONG))
    assert refused.value.kind == "rejected"


def test_it_is_built_from_the_stt_settings(tmp_path: Path) -> None:
    stt = SttSettings(live_language="classified", classifier_dir=tmp_path, classifier_threads=4)
    silero = SileroLanguage.from_settings(VoiceSettings(env="test", stt=stt))
    assert (silero.name, silero.folder, silero.threads) == ("silero", tmp_path, 4)
    asyncio.run(silero.aclose())
