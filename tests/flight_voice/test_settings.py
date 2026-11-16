"""The flight agent's settings (flight_voice/settings.py): its own under `FLIGHT_VOICE_` and the
library's under `T2V_`, a `.env` read only when given; each refusal naming the setting, never
its value; the runtime's folder always nested under the library's; 50 bookings a caller a day
unless set; the demo traveler the console's dev caller under `env` dev alone; and a persona's name
that would break the lines' rule refused, naming its setting."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from flight_voice.settings import ACTIONS_PER_DAY, APP_FOLDER, PREFIX, TOKENS_PER_DAY, load
from flight_voice.traveler import demo_caller
from t2_agentic_voice import ConfigurationError

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


def test_a_missing_access_code_is_refused(environment: pytest.MonkeyPatch) -> None:
    environment.delenv("FLIGHT_VOICE_ACCESS_CODE")
    assert "is not set" in _refused(["FLIGHT_VOICE_ACCESS_CODE"]).message


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


def test_the_demo_traveler_is_the_dev_caller_under_dev_alone(
    environment: pytest.MonkeyPatch,
) -> None:
    assert load().voice.server.dev_caller == demo_caller()
    environment.setenv("T2V_ENV", "test")
    assert load().voice.server.dev_caller is None
