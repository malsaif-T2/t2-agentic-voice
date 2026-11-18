"""The flight data's settings (flight_data/settings.py), read as the app's own: the mock by
default; a source the settings cannot run refused by `load` as one ConfigurationError naming
its settings, never an IndexError (serpapi with no key, the scripted agent off the mock,
recorded with today live); the key never shown; the flight data read alone for the smoke run;
the re-exports of settings.py; and `for_the_app` adding no send words and no yes over the
question for a lean agent that cannot book."""

from __future__ import annotations

from pathlib import Path

import pytest
from flight_voice import settings, voice_settings
from flight_voice.settings import load, load_flight_data
from flight_voice.voice_settings import YES_OVER_QUESTION, for_the_app
from t2_agentic_voice import ConfigurationError, VoiceSettings

from tests.leaks import holding, shown

KEY = "made-up-serpapi-key-zq9"


def _refused(names: list[str]) -> ConfigurationError:
    with pytest.raises(ConfigurationError) as raised:
        load()
    assert raised.value.details["settings"] == names
    assert "FIX" in raised.value.message
    return raised.value


def test_the_mock_is_the_default_and_every_setting_has_one(
    environment: pytest.MonkeyPatch,
) -> None:
    app = load().app
    assert app.flight_data == "mock" and app.serpapi_key is None
    assert (app.flight_data_deadline_s, app.flight_data_span_days) == (13.0, 14)
    assert (app.flight_data_span_concurrency, app.flight_data_span_deadline_s) == (14, 12.0)
    assert (app.flight_data_cache_s, app.serpapi_deep_search) == (600.0, False)
    assert app.flight_data_fixtures is None and app.flight_data_record_to is None


def test_serpapi_with_no_key_is_refused_naming_both_settings(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    environment.setenv("FLIGHT_VOICE_FLIGHT_DATA", "serpapi")
    _refused(["FLIGHT_VOICE_FLIGHT_DATA", "FLIGHT_VOICE_SERPAPI_KEY"])
    environment.setenv("FLIGHT_VOICE_SERPAPI_KEY", "   ")
    _refused(["FLIGHT_VOICE_FLIGHT_DATA", "FLIGHT_VOICE_SERPAPI_KEY"])


def test_the_scripted_agent_is_refused_off_the_mock(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("FLIGHT_VOICE_FLIGHT_DATA", "serpapi")
    environment.setenv("FLIGHT_VOICE_SERPAPI_KEY", KEY)
    error = _refused(["FLIGHT_VOICE_FLIGHT_DATA", "FLIGHT_VOICE_AGENT"])
    assert holding(KEY, shown(error)) == []


def test_recorded_with_today_live_is_refused(environment: pytest.MonkeyPatch) -> None:
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    environment.setenv("FLIGHT_VOICE_FLIGHT_DATA", "recorded")
    _refused(["FLIGHT_VOICE_FLIGHT_DATA", "FLIGHT_VOICE_TODAY"])
    environment.setenv("FLIGHT_VOICE_TODAY", "2026-11-18")
    assert load().app.flight_data == "recorded"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("FLIGHT_DATA", "amadeus-zq9"),
        ("FLIGHT_DATA_DEADLINE_S", "31"),
        ("FLIGHT_DATA_SPAN_DAYS", "63"),
        ("FLIGHT_DATA_SPAN_CONCURRENCY", "0"),
        ("FLIGHT_DATA_CACHE_S", "-1"),
    ],
)
def test_a_wrong_flight_data_value_is_refused_naming_its_setting(
    environment: pytest.MonkeyPatch, name: str, value: str
) -> None:
    environment.setenv("FLIGHT_VOICE_" + name, value)
    error = _refused(["FLIGHT_VOICE_" + name])
    assert value not in error.message


def test_the_key_is_never_shown(
    environment: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level("DEBUG")
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    environment.setenv("FLIGHT_VOICE_FLIGHT_DATA", "serpapi")
    environment.setenv("FLIGHT_VOICE_SERPAPI_KEY", KEY)
    app = load().app
    assert app.serpapi_key is not None and app.serpapi_key.get_secret_value() == KEY
    assert KEY not in repr(app) and KEY not in str(app.model_dump())
    environment.setenv("FLIGHT_VOICE_SERPAPI_DEEP_SEARCH", KEY)  # a key in the wrong place
    with pytest.raises(ConfigurationError) as raised:
        load()
    assert holding(KEY, shown(raised.value, caplog=caplog, capsys=capsys)) == []


def test_the_flight_data_is_read_alone_for_the_smoke_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert load_flight_data().serpapi_key is None  # no access code needed
    file = tmp_path / "smoke.env"
    file.write_bytes(f"FLIGHT_VOICE_SERPAPI_KEY={KEY}\n".encode())
    read = load_flight_data(file).serpapi_key
    assert read is not None and read.get_secret_value() == KEY
    monkeypatch.setenv("FLIGHT_VOICE_FLIGHT_DATA_SPAN_DAYS", "0")
    with pytest.raises(ConfigurationError) as raised:
        load_flight_data()
    assert raised.value.details["settings"] == ["FLIGHT_VOICE_FLIGHT_DATA_SPAN_DAYS"]


def test_the_re_exports_of_settings_still_import() -> None:
    for name in voice_settings.__all__:
        assert getattr(settings, name) is getattr(voice_settings, name), name


def test_a_lean_agent_that_cannot_book_gets_no_send_words_or_yes_over_its_question() -> None:
    voice = VoiceSettings(env="test")
    booking = for_the_app(voice, agent="lean")
    assert booking.words.send and getattr(booking.interruptions, YES_OVER_QUESTION)
    linking = for_the_app(voice, agent="lean", bookable=False)
    assert linking.words.send == {}
    assert not getattr(linking.interruptions, YES_OVER_QUESTION)
    assert linking.guard.plain_speech and linking.llm.max_requests_per_turn == 4
    scripted = for_the_app(voice, bookable=False)
    assert scripted.interruptions.yes_over_read_back  # the scripted agent's own, as before
