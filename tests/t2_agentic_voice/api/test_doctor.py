"""`t2v doctor` (api/doctor.py), against a fake text-to-speech: the key; each language's model and
voice with no synthesis; the ONNX files against the installed Pipecat's record; the clock and its
skew against the provider's, read from the language checks' answers; and, only with
`--synthesize`, one short request per language. Each failure says what to fix, never a value,
and the command fails."""

from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_tts import GroqTTS
from t2_agentic_voice.api.cli import main
from t2_agentic_voice.api.doctor import SAMPLES, Check, Wall, checks, onnx
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.tts import TtsSettings

from tests.t2_agentic_voice.adapters.groq_support import FakeGroq
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech

KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"
# The FIX line adapters/groq_tts.py gives a model whose terms are not accepted.
TERMS_FIX = (
    "FIX: accept the terms of canopylabs/orpheus-v1-english in Groq's console "
    "(console.groq.com/playground, with the model chosen), signed in as the key's "
    "organization's admin, then try again."
)
LANGUAGES = (
    '{"ar": {"model": "canopylabs/orpheus-arabic-saudi", "voice": "abdullah"}, '
    '"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}'
)
# This machine's time in the clock's tests: 0.4 s past a whole second, which Groq's Date lacks.
NOW = datetime(2026, 11, 4, 9, 15, 2, 400_000, tzinfo=UTC)
SET_CLOCK = "FIX: set this machine's clock: on Windows, Settings > Time & language"
UNMEASURED = "its skew was not measured: "


def _settings(tmp_path: Path, **groups: Any) -> VoiceSettings:
    groq = groups.pop("groq", GroqSettings(api_key=SecretStr(KEY)))
    groups.setdefault("tts", TtsSettings(provider="groq"))  # Orpheus, on the Groq key (D-114)
    return VoiceSettings(env="dev", groq=groq, **groups)


def _run(
    settings: VoiceSettings, tts: Any, *, synthesize: bool, wall: Wall = lambda: NOW
) -> list[Check]:
    providers = Providers(stt=FakeSpeechToText(), tts=tts)
    return asyncio.run(checks(settings, synthesize=synthesize, providers=providers, wall=wall))


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


def test_a_model_whose_terms_are_not_accepted_fails_with_its_fix_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The adapter's rejected `ProviderError` for Groq's `model_terms_required` carries its FIX
    line in its details (core/errors.py fixes the message per kind): `t2v doctor --synthesize`
    prints it after the message and the kind; a `fix` that is not a string is left out."""
    terms = ProviderError("rejected", False, details={"error": "model_terms_required"})
    terms.details["fix"] = TERMS_FIX
    odd = ProviderError("rejected", False, details={"fix": 7})
    failures = {SAMPLES["en"]: terms, SAMPLES["ar"]: odd}

    def fakes(cls: type[Providers], settings: VoiceSettings) -> Providers:
        tts = FakeTextToSpeech(languages=("ar", "en"), failures=failures)
        return Providers(stt=FakeSpeechToText(), tts=tts)

    monkeypatch.setattr(Providers, "from_settings", classmethod(fakes))
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_GROQ__API_KEY", KEY)
    monkeypatch.setenv("T2V_TTS__PROVIDER", "groq")  # Orpheus, the fallback (D-114)
    monkeypatch.setenv("T2V_TTS__LANGUAGES", LANGUAGES)
    assert main(["doctor", "--synthesize"]) == 1
    lines = capsys.readouterr().out.splitlines()
    [english] = [line for line in lines if line.startswith("FAIL  synthesis en")]
    assert english.endswith(f"(rejected) {TERMS_FIX}")
    [arabic] = [line for line in lines if line.startswith("FAIL  synthesis ar")]
    assert arabic.endswith("(rejected)")


def test_the_providers_it_built_are_each_closed_though_one_close_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every provider the settings built is closed after the checks, in order, the ones after a
    close that failed included; then the failure is raised."""

    class _Failing(FakeSpeechToText):
        async def aclose(self) -> None:
            await super().aclose()
            raise OSError("made-up close failure")

    stt, tts = _Failing(), FakeTextToSpeech()
    monkeypatch.setattr(
        Providers, "from_settings", classmethod(lambda cls, s: Providers(stt=stt, tts=tts))
    )
    with pytest.raises(OSError, match="made-up close failure"):
        asyncio.run(checks(_settings(tmp_path), synthesize=False))
    assert stt.closed and tts.closed


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
    assert named["clock"].detail.endswith(f"{UNMEASURED}no language check ran")


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
    monkeypatch.setenv("T2V_TTS__PROVIDER", "groq")  # Orpheus, the fallback (D-114)
    monkeypatch.setenv(
        "T2V_TTS__LANGUAGES", '{"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}'
    )
    assert main(["doctor"]) == 0


@pytest.mark.parametrize(
    ("allowed", "skew", "ok"),
    [
        (30, 0, True),
        (30, 12, True),
        (30, -12, True),
        (30, 29, True),  # at the allowance: 29 s and 1 s for the reading
        (30, -29, True),
        (30, 30, False),  # past it, since the reading may be 1 s short
        (30, -30, False),
        (30, 3600, False),
        (5, 4, True),
        (5, 5, False),
    ],
)
def test_the_clock_passes_while_its_skew_and_1_s_stay_within_the_allowance(
    tmp_path: Path, allowed: int, skew: int, ok: bool
) -> None:
    """The provider's time a whole second, as Groq's Date is, and this machine's 0.4 s past
    one: the skew is this machine's minus the provider's, signed and read to the second, and
    the check asks for no answer beyond the language checks'."""
    tts = FakeTextToSpeech(sent_at=NOW.replace(microsecond=0) - timedelta(seconds=skew))
    settings = _settings(tmp_path, join=JoinSettings(max_clock_skew_s=allowed))
    clock = _by_name(_run(settings, tts, synthesize=False))["clock"]
    assert clock.ok is ok
    assert clock.detail.startswith(
        "this machine's UTC time is 2026-11-04T09:15:02Z; its skew against fake's clock is "
        f"{skew:+d} s (this machine's minus fake's, read to the second), "
        f"{'within' if ok else 'past'} the {allowed} s join tokens allow (join.max_clock_skew_s)"
    )
    assert (SET_CLOCK in clock.detail) is not ok
    assert ("w32tm /resync" in clock.detail) is not ok
    assert tts.checked == ["ar-SA", "ar", "en"] and tts.calls == []


def test_the_skew_is_read_at_the_middle_of_the_last_check_that_gave_a_time(
    tmp_path: Path,
) -> None:
    """Each check's request takes 2 s on this machine's clock: en's, the last, runs from 8 s to
    10 s past NOW, so the skew is read 9.4 s past the provider's time."""
    ticks = itertools.count()

    def wall() -> datetime:
        return NOW + timedelta(seconds=2 * next(ticks))

    tts = FakeTextToSpeech(sent_at=NOW.replace(microsecond=0))
    clock = _by_name(_run(_settings(tmp_path), tts, synthesize=False, wall=wall))["clock"]
    assert clock.ok and clock.detail.startswith(
        "this machine's UTC time is 2026-11-04T09:15:11Z; its skew against fake's clock is +9 s"
    )


def test_with_no_time_given_or_no_check_passed_the_skew_is_not_measured(tmp_path: Path) -> None:
    timeless = _by_name(_run(_settings(tmp_path), FakeTextToSpeech(), synthesize=False))
    assert timeless["clock"].ok and timeless["clock"].detail.endswith(
        f"{UNMEASURED}no answer of fake's gave its time (an HTTP Date header)"
    )
    refused = FakeTextToSpeech(languages=(), sent_at=NOW - timedelta(hours=1))
    found = _by_name(_run(_settings(tmp_path), refused, synthesize=False))
    assert not found["model and voice en"].ok and found["clock"].ok
    assert found["clock"].detail == (
        "this machine's UTC time is 2026-11-04T09:15:02Z; join tokens are taken up to 30 s off "
        f"it (join.max_clock_skew_s); {UNMEASURED}no language check passed"
    )


LISTED = {
    "object": "list",
    "data": [
        {"object": "model", "created": 0, "owned_by": "made-up", "id": voice.model}
        for voice in TtsSettings(provider="groq").languages.values()
    ],
}


@pytest.mark.parametrize(
    ("date", "shown"),
    [
        (format_datetime(datetime(2026, 11, 4, 9, 15, 5, tzinfo=UTC), usegmt=True), "is -3 s"),
        (None, f"{UNMEASURED}no answer of groq's gave its time"),
        ("Wed, 32 Nov 2026 09:15:02 GMT", f"{UNMEASURED}no answer of groq's gave its time"),
        ("made-up", f"{UNMEASURED}no answer of groq's gave its time"),
    ],
)
def test_groqs_date_header_gives_the_skew_with_no_request_of_its_own(
    tmp_path: Path, date: str | None, shown: str
) -> None:
    """Through the Groq adapter on a fake transport: its Date is read from each model list the
    language checks ask for; a missing or malformed one leaves the skew unmeasured, never a
    failure; and no request is sent beyond one model list per language."""
    headers = {} if date is None else {"date": date}
    fake = FakeGroq(*(httpx.Response(200, json=LISTED, headers=headers) for _ in range(3)))
    settings = _settings(tmp_path)

    async def run() -> list[Check]:
        tts = GroqTTS.from_settings(settings, transport=fake)
        providers = Providers(stt=FakeSpeechToText(), tts=tts)
        try:
            return await checks(settings, synthesize=False, providers=providers, wall=lambda: NOW)
        finally:
            await tts.aclose()

    found = asyncio.run(run())
    clock = _by_name(found)["clock"]
    assert clock.ok and shown in clock.detail
    assert [(r.method, r.url.path) for r in fake.requests] == [("GET", "/openai/v1/models")] * 3
    assert all(KEY not in check.detail for check in found)


def test_t2v_doctor_prints_the_clocks_skew_and_fails_past_the_allowance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[datetime] = []

    def fakes(cls: type[Providers], settings: VoiceSettings) -> Providers:
        tts = FakeTextToSpeech(sent_at=sent[-1])
        return Providers(stt=FakeSpeechToText(), tts=tts)

    monkeypatch.setattr(Providers, "from_settings", classmethod(fakes))
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_GROQ__API_KEY", KEY)
    sent.append(datetime.now(UTC) - timedelta(hours=1))
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    [clock] = [line for line in out.splitlines() if line.startswith("FAIL  clock")]
    assert "its skew against fake's clock is +3600 s" in clock and SET_CLOCK in clock
    assert KEY not in out
    sent.append(datetime.now(UTC))
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    [clock] = [line for line in out.splitlines() if line.startswith("ok    clock")]
    assert "within the 30 s join tokens allow" in clock and KEY not in out
