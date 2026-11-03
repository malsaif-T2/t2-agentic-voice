"""`t2v doctor` (api/doctor.py), against a fake text-to-speech: the key; each language's model and
voice with no synthesis; the ONNX files against the installed Pipecat's record; the clock; and,
only with `--synthesize`, one short request per language. Each failure says what to fix, never a
value, and the command fails."""

from __future__ import annotations

import asyncio
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from t2_agentic_voice.api.cli import main
from t2_agentic_voice.api.doctor import SAMPLES, Check, checks, onnx
from t2_agentic_voice.api.runtime import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech

KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"


def _settings(tmp_path: Path, **groups: Any) -> VoiceSettings:
    groq = groups.pop("groq", GroqSettings(api_key=SecretStr(KEY)))
    return VoiceSettings(env="dev", groq=groq, **groups)


def _run(settings: VoiceSettings, tts: FakeTextToSpeech, *, synthesize: bool) -> list[Check]:
    providers = Providers(stt=FakeSpeechToText(), tts=tts)
    return asyncio.run(checks(settings, synthesize=synthesize, providers=providers))


def _by_name(found: list[Check]) -> dict[str, Check]:
    return {check.name: check for check in found}


def test_doctor_checks_each_language_with_no_synthesis(tmp_path: Path) -> None:
    tts = FakeTextToSpeech()
    found = _by_name(_run(_settings(tmp_path), tts, synthesize=False))
    assert found["key"].ok and tts.calls == []
    assert tts.checked == ["ar-SA", "ar", "en"]
    for tag in ("ar-SA", "ar", "en"):
        assert found[f"model and voice {tag}"].ok
    assert found["onnx silero_vad.onnx"].ok and found["onnx smart-turn-v3.2-cpu.onnx"].ok
    assert found["clock"].ok and "join.max_clock_skew_s" in found["clock"].detail


def test_synthesize_sends_one_short_request_per_language(tmp_path: Path) -> None:
    tts = FakeTextToSpeech(cut_short=(SAMPLES["en"],))
    found = _by_name(_run(_settings(tmp_path), tts, synthesize=True))
    assert tts.calls == [(SAMPLES["ar"], "ar-SA"), (SAMPLES["ar"], "ar"), (SAMPLES["en"], "en")]
    assert all(found[f"synthesis {tag}"].ok for tag in ("ar-SA", "ar", "en"))
    assert "cut short" in found["synthesis en"].detail


def test_a_language_or_a_synthesis_the_provider_refuses_fails(tmp_path: Path) -> None:
    refused = ProviderError("rejected", False, details={"status": 400})
    tts = FakeTextToSpeech(languages=("en",), failures={SAMPLES["en"]: refused})
    found = _by_name(_run(_settings(tmp_path), tts, synthesize=True))
    assert not found["model and voice ar-SA"].ok and "FIX:" in found["model and voice ar-SA"].detail
    assert not found["synthesis en"].ok and "(rejected)" in found["synthesis en"].detail


def test_a_synthesis_with_no_audio_fails(tmp_path: Path) -> None:
    found = _by_name(
        _run(_settings(tmp_path), FakeTextToSpeech(seconds_per_char=0), synthesize=True)
    )
    assert not found["synthesis en"].ok and "no audio" in found["synthesis en"].detail


def test_no_key_fails_and_the_rest_is_still_checked(tmp_path: Path) -> None:
    found = asyncio.run(checks(_settings(tmp_path, groq=GroqSettings()), synthesize=True))
    named = _by_name(found)
    assert not named["key"].ok and "T2V_GROQ__API_KEY" in named["key"].detail
    assert not named["providers"].ok and "FIX:" in named["providers"].detail
    assert named["clock"].ok and any(name.startswith("onnx ") for name in named)


def test_a_key_file_that_cannot_be_read_fails_naming_its_setting(tmp_path: Path) -> None:
    missing = tmp_path / "zx-missing-key"
    found = asyncio.run(
        checks(_settings(tmp_path, groq=GroqSettings(api_key_file=missing)), synthesize=False)
    )
    key = _by_name(found)["key"]
    assert not key.ok and "T2V_GROQ__API_KEY_FILE" in key.detail and str(missing) not in key.detail


class _File:
    """An installed file, as `importlib.metadata` gives one."""

    def __init__(self, name: str, data: bytes | None, recorded: str | None) -> None:
        self.name = name
        self.suffix = Path(name).suffix
        self._data = data
        self.hash = (
            None if recorded is None else type("H", (), {"mode": "sha256", "value": recorded})()
        )

    def read_binary(self) -> bytes:
        if self._data is None:
            raise FileNotFoundError(self.name)
        return self._data


class _Distribution:
    def __init__(self, *files: _File) -> None:
        self.files = list(files)


def test_an_onnx_file_that_differs_from_its_record_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    files = (_File("a.onnx", b"model", "zx-not-its-hash"), _File("b.onnx", None, None))
    monkeypatch.setattr(metadata, "distribution", lambda name: _Distribution(*files))
    found = onnx()
    assert [check.ok for check in found] == [False, False]
    assert "differs" in found[0].detail and "cannot be read" in found[1].detail
    assert all("FIX:" in check.detail for check in found)


def test_a_missing_pipecat_or_one_with_no_model_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "distribution", missing)
    assert [check.ok for check in onnx()] == [False]
    monkeypatch.setattr(metadata, "distribution", lambda name: _Distribution())
    [none] = onnx()
    assert not none.ok and "no ONNX model" in none.detail


def test_t2v_doctor_prints_each_check_and_fails_when_one_does(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    built: list[Providers] = []

    def fakes(cls: type[Providers], settings: VoiceSettings) -> Providers:
        built.append(Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech(languages=("en",))))
        return built[-1]

    monkeypatch.setattr(Providers, "from_settings", classmethod(fakes))
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_GROQ__API_KEY", KEY)
    assert main(["doctor", "--synthesize"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  model and voice ar-SA" in out and "ok    synthesis en" in out
    assert KEY not in out
    [providers] = built
    assert providers.tts.closed and providers.stt.closed  # type: ignore[attr-defined]
    monkeypatch.setenv(
        "T2V_TTS__LANGUAGES", '{"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}'
    )
    assert main(["doctor"]) == 0
