"""The flight agent's settings (flight_voice/settings.py): its own under `FLIGHT_VOICE_` and the
library's under `T2V_`, a `.env` read only when given; each refusal naming the setting, never
its value; the runtime's folder always nested under the library's; 50 bookings a caller a day,
the guard's two rules of run F's round 2, its plain speech (D-111) and a claim sent again on,
four model requests a turn, and a yes over the read-back held (D-108), each unless set; the
demo traveler the console's dev caller under `env` dev alone; and a persona's name that would
break the lines' rule refused, naming its setting."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from flight_voice.app_voice import SPOKEN_NUMBERS
from flight_voice.settings import (
    ACTIONS_PER_DAY,
    APP_FOLDER,
    GUARD_ON,
    PREFIX,
    REQUESTS_PER_TURN,
    TOKENS_PER_DAY,
    YES_OVER_READ_BACK,
    for_the_app,
    load,
)
from flight_voice.traveler import demo_caller
from t2_agentic_voice import ConfigurationError, GuardSettings, InterruptionSettings, VoiceSettings

from tests.flight_voice.server_support import CODE
from tests.isolation import FLIGHT_PREFIX


def _refused(names: list[str]) -> ConfigurationError:
    with pytest.raises(ConfigurationError) as raised:
        load()
    assert raised.value.details["settings"] == names
    return raised.value


def test_the_apps_prefix_is_the_one_the_suite_drops() -> None:
    assert PREFIX == FLIGHT_PREFIX


def test_both_settings_load_from_the_environment(environment: pytest.MonkeyPatch) -> None:
    loaded = load()
    assert loaded.app.access_code is not None
    assert loaded.app.access_code.get_secret_value() == CODE
    assert loaded.app.tokens_per_day == TOKENS_PER_DAY == 50
    assert loaded.app.today == "live"
    assert loaded.app.names().persona_name_en == "Saad"
    assert loaded.voice.join.current_kid == "k1"


def test_a_dotenv_file_is_read_only_when_given(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    file = tmp_path / "flight.env"
    file.write_bytes(b"FLIGHT_VOICE_TOKENS_PER_DAY=7\nFLIGHT_VOICE_TODAY=2026-11-16\n")
    assert load().app.tokens_per_day == TOKENS_PER_DAY
    loaded = load(file)
    assert loaded.app.tokens_per_day == 7
    assert loaded.app.today == date(2026, 11, 16)
    assert loaded.app.today_source()() == date(2026, 11, 16)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ACCESS_CODE", "short-code-0123"),
        ("WEBSITE_ORIGIN", "HTTPS://Example.com/"),
        ("TOKENS_PER_DAY", "0"),
        ("TODAY", "next-tuesday-zq9"),
        ("BOOKING_MODE", "explode-zq9"),
        ("SEARCH_MODE", "explode-zq9"),
        ("PROFILE_MODE", "slow"),
        ("SLOW_S", "-1"),
        ("AIRLINE_CODE", "t2-zq9"),
        ("PERSONA_NAME_EN", "Saad {zq9}"),
    ],
)
def test_a_wrong_value_is_refused_naming_its_setting_never_the_value(
    environment: pytest.MonkeyPatch, name: str, value: str
) -> None:
    environment.setenv(PREFIX + name, value)
    error = _refused([PREFIX + name])
    assert value not in error.message
    assert "zq9" not in error.message
    assert "FIX" in error.message


def test_no_access_code_opens_the_line(environment: pytest.MonkeyPatch) -> None:
    """The owner, 2026-11-19: "do not require Access code for users" (D-129)."""
    environment.delenv("FLIGHT_VOICE_ACCESS_CODE")
    assert load().app.access_code is None


def test_the_join_key_that_signs_is_required(environment: pytest.MonkeyPatch) -> None:
    environment.delenv("T2V_JOIN__CURRENT_KID")
    _refused(["T2V_JOIN__CURRENT_KID"])


@pytest.mark.parametrize(
    ("name", "value"),
    [("PERSONA_NAME_EN", "Wait"), ("PERSONA_NAME_AR", "لحظه"), ("AIRLINE_NAME_EN", "Okay Air")],
)
def test_a_name_that_breaks_the_lines_rule_is_refused_naming_its_setting(
    environment: pytest.MonkeyPatch, name: str, value: str
) -> None:
    environment.setenv(PREFIX + name, value)
    error = _refused([PREFIX + name])
    assert value not in error.message


def test_the_runtimes_folder_always_nests_under_the_librarys(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.setenv("T2V_STORAGE__VAR_DIR", str(tmp_path / "base"))
    assert load().voice.storage.var_dir == tmp_path / "base" / APP_FOLDER


def test_bookings_a_day_are_fifty_unless_the_environment_sets_them(
    environment: pytest.MonkeyPatch,
) -> None:
    assert load().voice.limits.actions_per_caller_per_day == ACTIONS_PER_DAY == 50
    environment.setenv("T2V_LIMITS__ACTIONS_PER_CALLER_PER_DAY", "3")
    assert load().voice.limits.actions_per_caller_per_day == 3


def test_the_guards_rules_and_four_requests_a_turn_hold_unless_set(
    environment: pytest.MonkeyPatch,
) -> None:
    voice = load().voice
    assert GUARD_ON == (
        "question_stop_drops_calls",
        "drop_stage_notes",
        "plain_speech",
        "retry_claims",
    )
    assert (voice.guard.question_stop_drops_calls, voice.guard.drop_stage_notes) == (True, True)
    assert voice.guard.plain_speech and voice.guard.retry_claims
    assert voice.llm.max_requests_per_turn == REQUESTS_PER_TURN == 4
    environment.setenv("T2V_GUARD__QUESTION_STOP_DROPS_CALLS", "false")
    environment.setenv("T2V_GUARD__QUESTIONS_PER_REPLY", "2")
    environment.setenv("T2V_LLM__MAX_REQUESTS_PER_TURN", "3")
    voice = load().voice
    assert (voice.guard.question_stop_drops_calls, voice.guard.drop_stage_notes) == (False, True)
    assert (voice.guard.questions_per_reply, voice.llm.max_requests_per_turn) == (2, 3)
    # In code, as run F builds its settings: a group's field set there is kept.
    given = VoiceSettings(env="test", guard=GuardSettings(drop_stage_notes=False))
    app = for_the_app(given)
    assert (app.guard.question_stop_drops_calls, app.guard.drop_stage_notes) == (True, False)
    assert app.llm.max_requests_per_turn == 4 and given.llm.max_requests_per_turn == 3
    assert app.guard.plain_speech and not given.guard.plain_speech


def test_plain_speech_is_off_when_the_environment_sets_it_so(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("T2V_GUARD__PLAIN_SPEECH", "false")
    voice = load().voice
    assert not voice.guard.plain_speech and voice.guard.drop_stage_notes


def test_a_yes_over_the_read_back_is_held_unless_the_environment_sets_it(
    environment: pytest.MonkeyPatch,
) -> None:
    """D-108: the owner's "Any yes books", on for the flight agent; the library's default off."""
    assert YES_OVER_READ_BACK == "yes_over_read_back"
    assert not VoiceSettings(env="test").interruptions.yes_over_read_back
    voice = load().voice
    assert voice.interruptions.yes_over_read_back
    assert voice.interruptions.mode == "two_step"  # the held yes is two_step's
    environment.setenv("T2V_INTERRUPTIONS__YES_OVER_READ_BACK", "false")
    assert not load().voice.interruptions.yes_over_read_back
    environment.delenv("T2V_INTERRUPTIONS__YES_OVER_READ_BACK")
    environment.setenv("T2V_INTERRUPTIONS__DUCK_LEVEL", "0.5")  # another field set: still on
    voice = load().voice
    assert voice.interruptions.yes_over_read_back and voice.interruptions.duck_level == 0.5
    # In code: a group's field set there is kept.
    off = InterruptionSettings(yes_over_read_back=False)
    assert not for_the_app(
        VoiceSettings(env="test", interruptions=off)
    ).interruptions.yes_over_read_back


def test_saad_speaks_in_groqs_voices_unless_the_environment_names_elevenlabs(
    environment: pytest.MonkeyPatch,
) -> None:
    """The owner, 2026-11-18: back to Groq's Orpheus for its credits (app_voice.py); the
    library's default stays ElevenLabs (D-114), and the owner's ElevenLabs voice comes back with
    `T2V_TTS__PROVIDER=elevenlabs`."""
    assert VoiceSettings(env="test").tts.provider == "elevenlabs"
    tts = load().voice.tts
    assert tts.provider == "groq" and tts.spoken_numbers == SPOKEN_NUMBERS
    assert {tag: (v.model, v.voice) for tag, v in tts.languages.items()} == {
        "ar-SA": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "ar": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "en": ("canopylabs/orpheus-v1-english", "troy"),
    }
    environment.setenv("T2V_TTS__PROVIDER", "elevenlabs")
    tts = load().voice.tts
    assert tts.provider == "elevenlabs" and tts.spoken_numbers == SPOKEN_NUMBERS
    assert tts.languages["ar-SA"].voice == "nhJWWCFdNdusuVUT3x19"


def test_numbers_and_times_are_said_in_the_callers_register_unless_set(
    environment: pytest.MonkeyPatch,
) -> None:
    """D-107 for the flight agent: "14:00" is said as a clock says it, never digit by digit."""
    assert VoiceSettings(env="test").tts.spoken_numbers == "as_written"
    assert load().voice.tts.spoken_numbers == SPOKEN_NUMBERS == "by_register"
    environment.setenv("T2V_TTS__SPOKEN_NUMBERS", "as_written")
    assert load().voice.tts.spoken_numbers == "as_written"


def test_the_demo_traveler_is_the_dev_caller_under_dev_alone(
    environment: pytest.MonkeyPatch,
) -> None:
    assert load().voice.server.dev_caller == demo_caller()
    environment.setenv("T2V_ENV", "test")
    assert load().voice.server.dev_caller is None
