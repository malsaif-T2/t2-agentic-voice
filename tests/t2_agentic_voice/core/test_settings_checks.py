"""The checks the settings make as they load: what each `env` refuses (staging holds every
check prod holds: the design's 7.4), the bounds and shapes of the groups' values, and how every
setting is named and described (the design's 7.3 and 7.7)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from t2_agentic_voice.api.status import status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.tts import TtsSettings

from tests.t2_agentic_voice.core.settings_support import PREFIX, fields, nested

# Each check `env` makes: the setting, the value it refuses, and the environments that refuse it.
CHECKS = [
    (("server", "dev_page"), True, ("test", "staging", "prod")),
    (("logging", "content"), True, ("test", "staging", "prod")),
    (("logging", "level"), "DEBUG", ("staging", "prod")),
]
REFUSED = [(location, value, env) for location, value, envs in CHECKS for env in envs]
ALLOWED = [
    (location, value, env)
    for location, value, envs in CHECKS
    for env in ("dev", "test", "staging", "prod")
    if env not in envs
]
# Settings with no unit: a ratio from 0 to 1.
RATIOS = {("turns", "vad_confidence"), ("turns", "vad_min_volume")}


def _name(location: tuple[str, ...]) -> str:
    return PREFIX + "__".join(part.upper() for part in location)


@pytest.mark.parametrize(("location", "value", "env"), REFUSED)
def test_each_check_holds_in_its_environments_as_the_settings_load(
    location: tuple[str, str], value: object, env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every check that holds in prod holds in staging too, one test each, whether the settings
    come from the environment or from code."""
    monkeypatch.setenv(f"{PREFIX}ENV", env)
    monkeypatch.setenv(_name(location), str(value).lower() if value is True else str(value))
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert raised.value.message.startswith(f"{_name(location)} ")
    assert f"env={env} refuses. FIX:" in raised.value.message
    assert raised.value.details == {"setting": _name(location), "env": env}
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)
    with pytest.raises(ConfigurationError, match=_name(location)):
        VoiceSettings.model_validate({"env": env} | nested(location, value))


@pytest.mark.parametrize(("location", "value", "env"), REFUSED)
def test_status_makes_each_check_again_for_settings_copied_with_a_change(
    location: tuple[str, str], value: object, env: str
) -> None:
    """A copy is not validated again; `status` checks it before it reports it."""
    group, field = location
    base = VoiceSettings(env="dev")
    changed = getattr(base, group).model_copy(update={field: value})
    unsafe = base.model_copy(update={"env": env, group: changed})
    with pytest.raises(ConfigurationError, match=_name(location)) as raised:
        status(unsafe)
    assert raised.value.code == "configuration_error"


@pytest.mark.parametrize(("location", "value", "env"), ALLOWED)
def test_each_check_lets_the_other_environments_run(
    location: tuple[str, str], value: object, env: str
) -> None:
    settings = VoiceSettings.model_validate({"env": env} | nested(location, value))
    assert status(settings).env == env


def test_the_defaults_pass_every_check_in_every_environment() -> None:
    for env in ("dev", "test", "staging", "prod"):
        assert VoiceSettings.model_validate({"env": env}).env == env


def test_a_check_names_the_setting_under_the_prefix_it_was_loaded_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HELPDESK_VOICE_ENV", "staging")
    monkeypatch.setenv("HELPDESK_VOICE_LOGGING__LEVEL", "DEBUG")
    with pytest.raises(ConfigurationError, match=r"^HELPDESK_VOICE_LOGGING__LEVEL is DEBUG"):
        VoiceSettings.from_env(prefix="HELPDESK_VOICE_")


@pytest.mark.parametrize(
    ("group", "values"),
    [
        (ServerSettings, {"forwarded_allow_ips": ("*",)}),  # every peer could forge its address
        (ServerSettings, {"forwarded_allow_ips": ("127.0.0.1", " * ")}),
        (ServerSettings, {"forwarded_allow_ips": ("not-an-address",)}),
        (ServerSettings, {"turn_ttl_s": 86_401}),  # longer than a day
        (ServerSettings, {"turn_ttl_s": 0}),
        (ServerSettings, {"public_url": "voice.example"}),
        (ServerSettings, {"allowed_origins": ("https://www.example.com/",)}),  # a path: no origin
        (ServerSettings, {"allowed_origins": ("https://www.example.com?x=1",)}),
        (ServerSettings, {"allowed_origins": ("ftp://www.example.com",)}),
        (ServerSettings, {"ice_servers": ("https://turn.example",)}),
        (ServerSettings, {"ice_servers": ("turn:",)}),
        (ServerSettings, {"ice_servers": ("turn:turn example",)}),
        (TtsSettings, {"languages": {"fr": {"model": "canopylabs/orpheus-v1-english"}}}),
        (TtsSettings, {"languages": {"en": {"model": "playai-tts", "voice": "troy"}}}),
        (TtsSettings, {"languages": {"en": {"model": "canopylabs/orpheus-v1-english"}}}),
        (
            TtsSettings,
            {"languages": {"en": {"model": "canopylabs/orpheus-v1-english", "voice": "Troy"}}},
        ),
        (TtsSettings, {"timeout_s": 0}),
        (LoggingSettings, {"pipecat": "forward"}),
    ],
)
def test_a_group_refuses_a_value_out_of_its_bounds(
    group: type[BaseModel], values: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        group.model_validate(values)


@pytest.mark.parametrize(
    "values",
    [
        {"forwarded_allow_ips": ("127.0.0.1", "10.0.0.0/8", "::1")},
        {"allowed_origins": ("https://www.example.com", "http://localhost:8000")},
        {"ice_servers": ("stun:stun.example:3478", "turns:turn.example:443?transport=tcp")},
        {"public_url": "https://voice.example", "turn_ttl_s": 86_400},
    ],
)
def test_the_server_group_takes_what_it_documents(values: dict[str, Any]) -> None:
    assert ServerSettings.model_validate(values).model_dump(include=set(values)) == values


@pytest.mark.parametrize(
    ("location", "value"),
    [
        (("join", "ttl_s"), 121),  # a join token lives 120 s at most (the design's 6.5)
        (("join", "ttl_s"), 0),
        (("join", "max_clock_skew_s"), -1),
        (("join", "current_kid"), "a kid with spaces"),
        (("privacy", "consent_version"), ""),
        (("privacy", "consent_version"), "v" * 65),
        (("turns", "vad_confidence"), 1.5),
        (("turns", "vad_min_volume"), -0.1),
        (("turns", "vad_stop_ms"), 0),
        (("turns", "smart_turn_max_duration_s"), float("inf")),
        (("limits", "max_call_s"), 0),
        (("limits", "idle_s"), float("nan")),
    ],
)
def test_a_value_out_of_its_bounds_is_refused(location: tuple[str, str], value: object) -> None:
    with pytest.raises(ValidationError):
        VoiceSettings.model_validate({"env": "test"} | nested(location, value))


def test_the_turn_tts_and_limit_defaults_are_the_plans() -> None:
    """The decision log's starting values (plan 003), Q4's limits and Q5's voices."""
    settings = VoiceSettings(env="test")
    turns = settings.turns.model_dump()
    assert turns == {
        "vad_confidence": 0.7,
        "vad_start_ms": 200,
        "vad_stop_ms": 200,
        "vad_min_volume": 0.6,
        "smart_turn": True,
        "smart_turn_stop_ms": 3000,
        "smart_turn_pre_speech_ms": 500,
        "smart_turn_max_duration_s": 8.0,
        "max_silence_ms": 3000,
    }
    voices = {tag: (v.model, v.voice) for tag, v in settings.tts.languages.items()}
    assert voices == {
        "ar-SA": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "ar": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "en": ("canopylabs/orpheus-v1-english", "troy"),
    }
    assert (settings.tts.cache_phrases, settings.tts.trim_silence) == (True, False)
    assert (settings.limits.max_call_s, settings.limits.idle_s) == (600.0, 120.0)
    assert (settings.session.mode, settings.logging.pipecat) == ("echo", "off")
    assert (settings.privacy.record_audio, settings.privacy.consent_version) == (False, None)
    assert (settings.server.turn_ttl_s, settings.server.forwarded_allow_ips) == (3600, ())
    assert (settings.join.ttl_s, settings.join.max_clock_skew_s) == (60, 30)


def test_every_timing_or_size_setting_has_its_unit_in_its_name() -> None:
    """The design's 7.3: `_ms` or `_s`; only a ratio from 0 to 1 has none."""
    numbers = [loc for loc, kind in fields() if kind in (int, float)]
    unnamed = [loc for loc in numbers if not loc[-1].endswith(("_ms", "_s")) and loc not in RATIOS]
    assert numbers and unnamed == []


def test_every_setting_and_group_is_described() -> None:
    """The reference takes each description from the field itself (scripts/settings_ref.py)."""
    assert [location for location, described in _described() if not described] == []


def _described() -> list[tuple[tuple[str, ...], bool]]:
    found: list[tuple[tuple[str, ...], bool]] = []
    for name, field in VoiceSettings.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            found.append(((name,), bool(kind.__doc__)))
            found += [((name, n), bool(f.description)) for n, f in kind.model_fields.items()]
        else:
            found.append(((name,), bool(field.description)))
    return found
