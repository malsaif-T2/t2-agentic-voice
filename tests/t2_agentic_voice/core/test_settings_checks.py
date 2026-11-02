"""The checks the settings make as they load: what each `env` refuses (staging holds every
check prod holds: the design's 7.4), the bounds and shapes of the groups' values, and how every
setting is named and described (the design's 7.3 and 7.7)."""

from __future__ import annotations

import copy
import pickle
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr, ValidationError
from t2_agentic_voice.api.status import status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.join import MAX_CLOCK_SKEW_S, MAX_TTL_S
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from uvicorn.middleware.proxy_headers import _TrustedHosts

from tests.t2_agentic_voice.core.settings_support import LONG_SECRET, PREFIX, fields, nested

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
        (ServerSettings, {"forwarded_allow_ips": ("0.0.0.0/0",)}),  # "*" by another name
        (ServerSettings, {"forwarded_allow_ips": ("::/0",)}),
        (ServerSettings, {"forwarded_allow_ips": ("10.1.2.3/0",)}),
        (ServerSettings, {"forwarded_allow_ips": ("10.0.0.0/7",)}),  # wider than /8
        (ServerSettings, {"forwarded_allow_ips": ("2001:db8::/31",)}),  # wider than /32
        (ServerSettings, {"forwarded_allow_ips": ("::ffff:0:0/96",)}),  # every IPv4 peer, mapped
        (ServerSettings, {"forwarded_allow_ips": ("::/32",)}),  # holds the mapped ones too
        (ServerSettings, {"forwarded_allow_ips": ("64:ff9b::/96",)}),  # every IPv4 peer, NAT64
        (ServerSettings, {"forwarded_allow_ips": ("10.0.0.5/24",)}),  # host bits: matches none
        (ServerSettings, {"turn_ttl_s": 86_401}),  # longer than a day
        (ServerSettings, {"turn_ttl_s": 0}),
        (ServerSettings, {"public_url": "voice.example"}),
        (ServerSettings, {"allowed_origins": ("https://www.example.com/",)}),  # a path: no origin
        (ServerSettings, {"allowed_origins": ("https://www.example.com?x=1",)}),
        (ServerSettings, {"allowed_origins": ("ftp://www.example.com",)}),
        # Not as a browser sends it, so CORS, which compares text, would refuse the real page.
        (ServerSettings, {"allowed_origins": ("https://Example.com",)}),
        (ServerSettings, {"allowed_origins": ("HTTPS://example.com",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com:443",)}),
        (ServerSettings, {"allowed_origins": ("http://example.com:80",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com:0443",)}),
        (ServerSettings, {"allowed_origins": ("https://bücher.example",)}),
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


def test_the_proxy_and_origin_refusals_say_what_to_write() -> None:
    """Each refusal names the entry by its index and says what to write, never the value."""
    cases = [
        ("forwarded_allow_ips", "0.0.0.0/0", "entry 0 is wider than /8 for IPv4 or /32 for IPv6"),
        ("forwarded_allow_ips", "192.168.1.10/24", "give the network's own address, such as"),
        ("allowed_origins", "https://Example.com:443", "write the scheme and the host in lower"),
    ]
    for field, value, why in cases:
        with pytest.raises(ValidationError, match=why) as raised:
            ServerSettings.model_validate({field: (value,)})
        assert value not in str(raised.value)


@pytest.mark.parametrize(
    "values",
    [
        {"forwarded_allow_ips": ("127.0.0.1", "10.0.0.0/8", "::1", "2001:db8::/32")},
        {"forwarded_allow_ips": ("10.0.0.0/24", "::ffff:10.0.0.0/104", "::ffff:10.0.0.5")},
        {"forwarded_allow_ips": ("64:ff9b::a00:0/104", "2001:db8::/48")},
        {"allowed_origins": ("https://www.example.com", "http://localhost:8000")},
        {"allowed_origins": ("https://example.com:8443", "http://[::1]:8000", "http://[::1]")},
        {"ice_servers": ("stun:stun.example:3478", "turns:turn.example:443?transport=tcp")},
        {"public_url": "https://voice.example", "turn_ttl_s": 86_400},
    ],
)
def test_the_server_group_takes_what_it_documents(values: dict[str, Any]) -> None:
    assert ServerSettings.model_validate(values).model_dump(include=set(values)) == values


def test_every_trusted_proxy_the_settings_take_is_one_uvicorn_matches() -> None:
    """uvicorn reads each entry strictly and keeps one it cannot read as a name that matches no
    peer; so every entry the settings take is a network or an address to uvicorn, and a
    network's own peers are trusted, while a peer outside every entry is not."""
    entries = ("127.0.0.1", "10.0.0.0/24", "::1", "2001:db8::/32", "::ffff:10.0.0.0/104")
    trusted = _TrustedHosts(list(ServerSettings(forwarded_allow_ips=entries).forwarded_allow_ips))
    assert trusted.trusted_literals == set() and not trusted.always_trust
    assert all(peer in trusted for peer in ("10.0.0.7", "2001:db8::9", "::ffff:10.0.0.9"))
    assert not any(peer in trusted for peer in ("203.0.113.9", "10.0.1.1", "::ffff:1.2.3.4"))


@pytest.mark.parametrize(
    ("location", "value"),
    [
        (("join", "ttl_s"), 121),  # a join token lives 120 s at most (the design's 6.5)
        (("join", "ttl_s"), 0),
        (("join", "max_clock_skew_s"), -1),
        (("join", "max_clock_skew_s"), 61),  # a token verifies until its expiry plus this
        (("join", "max_clock_skew_s"), 86_400),
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
    with pytest.raises(ConfigurationError, match=f"cannot load: {_name(location)} "):
        VoiceSettings.model_validate({"env": "test"} | nested(location, value))


def test_the_join_bounds_hold_the_tokens_lifetime() -> None:
    """A token verifies until its expiry plus the skew: both bounds, at their most, load."""
    join = VoiceSettings.model_validate(
        {"env": "prod", "join": {"ttl_s": MAX_TTL_S, "max_clock_skew_s": MAX_CLOCK_SKEW_S}}
    ).join
    assert (join.ttl_s, join.max_clock_skew_s) == (120, 60)


def test_a_map_setting_cannot_change_once_loaded() -> None:
    """A group is read-only, its maps too, so no join key under 32 bytes reaches
    `resolved_keys` past the check and no call changes the voice every call shares; each map
    still dumps as the plain object it was given as."""
    loaded = VoiceSettings.model_validate(
        {"env": "test", "join": {"keys": {"k1": LONG_SECRET}, "current_kid": "k1"}}
    )
    copies = (
        loaded.model_copy(deep=True),
        copy.deepcopy(loaded),
        pickle.loads(pickle.dumps(loaded)),  # noqa: S301 - loads only bytes it dumped
    )
    for settings in (loaded, VoiceSettings(env="test"), *copies):
        keys: Any = settings.join.keys
        languages: Any = settings.tts.languages
        with pytest.raises(TypeError):
            keys["weak"] = SecretStr("short")
        with pytest.raises(TypeError):
            languages["en"] = languages["ar"]
        with pytest.raises(TypeError):
            keys._items["weak"] = SecretStr("short")
        dumped = settings.model_dump()
        assert type(dumped["join"]["keys"]) is dict and type(dumped["tts"]["languages"]) is dict
    assert all(each == loaded for each in copies)
    assert list(loaded.join.resolved_keys()) == ["k1"]
    assert loaded.model_dump(mode="json")["join"]["keys"] == {"k1": "**********"}
    assert LONG_SECRET not in repr(loaded.join.keys) and "k1" in repr(loaded.join.keys)


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
