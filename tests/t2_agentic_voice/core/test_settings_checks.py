"""The checks the settings make as they load: what each `env` refuses (staging holds every
check prod holds: the design's 7.4), the bounds and shapes of the groups' values, and how every
setting is named and described (the design's 7.3 and 7.7). That nothing changes them once
built: test_settings_read_only.py."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from t2_agentic_voice.api.status import status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings import server
from t2_agentic_voice.core.settings.join import MAX_CLOCK_SKEW_S, MAX_TTL_S
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from uvicorn.middleware.proxy_headers import _TrustedHosts

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
RATIOS = {
    ("turns", "vad_confidence"),
    ("turns", "vad_min_volume"),
    ("turns", "smart_turn_threshold"),
    ("interruptions", "duck_level"),
    ("stt", "classifier_min_share"),
    ("stt", "switch_min_probability"),
}


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
        # More than an IPv4 /8 of an IPv6 range that carries IPv4 addresses: nearly every IPv4
        # peer, mapped, translated (SIIT), through NAT64 (both prefixes), IPv4-compatible.
        (ServerSettings, {"forwarded_allow_ips": ("::ffff:0:0/96",)}),
        (ServerSettings, {"forwarded_allow_ips": ("::ffff:0:0/100",)}),
        (ServerSettings, {"forwarded_allow_ips": ("::/32",)}),  # holds the mapped ones too
        (ServerSettings, {"forwarded_allow_ips": ("::/64",)}),
        (ServerSettings, {"forwarded_allow_ips": ("::/96",)}),
        (ServerSettings, {"forwarded_allow_ips": ("::ffff:0:0:0/96",)}),
        (ServerSettings, {"forwarded_allow_ips": ("64:ff9b::/96",)}),
        (ServerSettings, {"forwarded_allow_ips": ("64:ff9b:1::/48",)}),
        (ServerSettings, {"forwarded_allow_ips": ("64:ff9b:1::/96",)}),
        (ServerSettings, {"forwarded_allow_ips": ("64:ff9b:1:ab00::/56",)}),  # another layout
        (ServerSettings, {"forwarded_allow_ips": ("2002::/16",)}),  # 6to4: every IPv4 peer
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
        # A host a browser decodes, cuts or refuses, or reads as another address.
        (ServerSettings, {"allowed_origins": ("https://exa%6dple.com",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com\\",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com\\path",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com\x00",)}),
        (ServerSettings, {"allowed_origins": ("https://ex\x00ample.com",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com\x7f",)}),
        (ServerSettings, {"allowed_origins": ("https://my_host.example",)}),
        (ServerSettings, {"allowed_origins": ("https://example.com.",)}),
        (ServerSettings, {"allowed_origins": ("http://127.1",)}),
        (ServerSettings, {"allowed_origins": ("http://010.0.0.1",)}),
        (ServerSettings, {"allowed_origins": ("http://0x7f.0.0.1",)}),
        (ServerSettings, {"allowed_origins": ("http://[fe80::1%25eth0]",)}),
        (ServerSettings, {"allowed_origins": ("http://[0:0:0:0:0:0:0:1]",)}),
        (ServerSettings, {"allowed_origins": ("http://[::ffff:1.2.3.4]",)}),
        (ServerSettings, {"allowed_origins": ("http://[2001:db8:0:0:1::1]",)}),
        (ServerSettings, {"allowed_origins": ("http://[2001:db8::1:2:3:4:5]",)}),  # one zero
        (ServerSettings, {"allowed_origins": ("http://[v1.x]",)}),  # no IP address at all
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
    """Each refusal names the entry by its index and says why, true of that entry, and what to
    write, the whole rule for a proxy; never the value."""
    wide = "entry 0 is wider than /8 for IPv4 or /32 for IPv6"
    carried = "entry 0 holds more than an IPv4 /8 of an IPv6 range that carries IPv4 addresses"
    cases = [
        ("forwarded_allow_ips", "0.0.0.0/0", wide),
        ("forwarded_allow_ips", "2001:db8::/31", wide),
        ("forwarded_allow_ips", "::/32", carried),  # exactly /32, so not wider than it
        ("forwarded_allow_ips", "::ffff:0:0/100", carried),
        ("forwarded_allow_ips", "64:ff9b:1::/96", carried),
        ("forwarded_allow_ips", "192.168.1.10/24", "give the network's own address, such as"),
        ("allowed_origins", "https://Example.com:443", "write the scheme in lowercase; the host"),
        ("allowed_origins", "https://exa%6dple.com", "letters, digits and hyphens between dots"),
    ]
    for field, value, why in cases:
        with pytest.raises(ValidationError, match=why) as raised:
            ServerSettings.model_validate({field: (value,)})
        assert value not in str(raised.value)
        if field == "forwarded_allow_ips" and "host bits" not in str(raised.value):
            assert "name each proxy: an entry is no wider than /8 for IPv4" in str(raised.value)


def test_the_proxy_rule_names_every_range_that_carries_ipv4_with_its_bound() -> None:
    """The setting's description (and so the reference) and each refusal state the rule whole:
    every range the check holds to IPv4's /8, with the widest entry it takes."""
    described = ServerSettings.model_fields["forwarded_allow_ips"].description or ""
    parts = re.split(r"/(\d+) where it overlaps ", described)
    stated = {
        ipaddress.ip_network(carrier): int(widest)
        for widest, ranges in zip(parts[1::2], parts[2::2], strict=True)
        for carrier in re.findall(r"[0-9a-f:]+/\d+", ranges)
    }
    assert stated == dict(server._EMBEDDED)
    assert "no wider than /8 for IPv4 or /32 for IPv6" in parts[0]


@pytest.mark.parametrize(
    "values",
    [
        {"forwarded_allow_ips": ("127.0.0.1", "10.0.0.0/8", "::1", "2001:db8::/32")},
        {"forwarded_allow_ips": ("10.0.0.0/24", "::ffff:10.0.0.0/104", "::ffff:10.0.0.5")},
        {"forwarded_allow_ips": ("64:ff9b::a00:0/104", "2001:db8::/48", "::1")},
        {"forwarded_allow_ips": ("64:ff9b:1::a00:0/104", "::ffff:0:a00:0/104", "::a00:0/104")},
        {"forwarded_allow_ips": ("2002:c000:204::/48",)},  # 6to4 of one IPv4 address
        {"allowed_origins": ("https://www.example.com", "http://localhost:8000")},
        {"allowed_origins": ("https://example.com:8443", "http://[::1]:8000", "http://[::1]")},
        {"allowed_origins": ("https://xn--bcher-kva.example", "http://127.0.0.1:8000")},
        {"allowed_origins": ("http://[::ffff:102:304]", "http://[2001:db8::1:0:0:1]:8443")},
        {"allowed_origins": ("http://[2001:db8:0:1:2:3:4:5]", "http://[::]")},
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
        (("turns", "smart_turn_threshold"), 1.5),
        (("turns", "complete_hold_ms"), -1),
        (("turns", "complete_hold_ms"), 1001),  # above the hold's bound (MAX_COMPLETE_HOLD_MS)
        (("stt", "no_speech_max"), -0.1),
        (("interruptions", "mode"), "pause"),
        (("interruptions", "duck_level"), 1.5),
        (("interruptions", "first_window_ms"), 0),
        (("interruptions", "min_words"), 0),
        (("interruptions", "short_s"), float("nan")),
        (("words", "stop"), {"fr": ["x"]}),
        (("words", "backchannel"), {"en": [""]}),
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


def test_the_turn_tts_and_limit_defaults_are_the_plans() -> None:
    """The decision log's starting values (plan 003), with plan 005's hold after Smart Turn's
    "complete" (E's arm Ec, 600 ms), Q4's limits and Q5's voices."""
    settings = VoiceSettings(env="test")
    turns = settings.turns.model_dump()
    assert turns == {
        "vad_confidence": 0.7,
        "vad_start_ms": 200,
        "vad_stop_ms": 200,
        "vad_min_volume": 0.6,
        "smart_turn": True,
        "smart_turn_threshold": 0.5,
        "complete_hold_ms": 600,
        "early_at_stop": False,  # the held request at Smart Turn's verdict (plan 010's 2.2)
        "smart_turn_stop_ms": 3000,
        "smart_turn_pre_speech_ms": 500,
        "smart_turn_threads": 1,
        "smart_turn_max_duration_s": 8.0,
        "max_silence_ms": 3000,
        "read_back_silence_ms": None,
    }
    voices = {tag: (v.model, v.voice) for tag, v in settings.tts.languages.items()}
    assert settings.tts.provider == "elevenlabs"  # the owner's pick (D-114); Groq the fallback
    assert voices == dict.fromkeys(
        ("ar-SA", "ar", "en"), ("eleven_v4_turbo", "nhJWWCFdNdusuVUT3x19")
    )
    assert (settings.tts.cache_phrases, settings.tts.trim_silence) == (True, False)
    assert (settings.limits.max_call_s, settings.limits.idle_s) == (600.0, 120.0)
    assert (settings.session.mode, settings.logging.pipecat) == (None, "off")  # the declaration's
    assert settings.session.progress_beat_ms is None  # D-077's 400 ms beat after a progress line
    assert not settings.session.early_over_reply  # no early start over a reply (TD-117)
    assert (settings.privacy.record_audio, settings.privacy.consent_version) == (False, None)
    assert (settings.server.turn_ttl_s, settings.server.forwarded_allow_ips) == (3600, ())
    assert (settings.join.ttl_s, settings.join.max_clock_skew_s) == (60, 30)


def test_the_interruption_and_word_defaults_are_plan_005s() -> None:
    """The two-step interruption, by the owner's ruling of 2026-11-06 (plan 005), the
    prototype's duck level, run W3's window and the starting rule's bounds, the short output's
    as the rule's one revision set it (1.2 s); no word added, nor a Saudi form, the caller's
    register not read Saudi first nor held fixed, nor a short turn's language held (GP-18;
    D-139); the filter for text from silence
    on, as the registered rule F and its one revision set it (0.55 and the caption list); a yes
    over a read-back's summary counting for nothing, as before D-108's setting, and a yes over a
    reply's closing question let go, as before D-116's (GP-18)."""
    settings = VoiceSettings(env="test")
    assert settings.interruptions.model_dump() == {
        "mode": "two_step",
        "duck_level": 0.25,
        "first_window_ms": 750,
        "min_words": 2,
        "short_words": 2,
        "short_s": 1.2,
        "own_words_s": 5.0,
        "yes_over_read_back": False,
        "answer_yes_over_question": False,
    }
    kinds = ("stop", "wait", "repeat", "backchannel", "no", "yes", "send")
    unlisted = {"vocabulary": (), "dialect": (), "saudi_first": False, "fixed_register": None}
    unlisted |= {"hold_reply_language": False}  # a short turn answered as heard (D-139)
    assert settings.words.model_dump() == {kind: {} for kind in kinds} | unlisted
    assert (settings.stt.no_speech_max, settings.stt.caption_filter) == (0.55, True)
    words = VoiceSettings.model_validate({"env": "test", "words": {"stop": {"en": ["x", "y"]}}})
    assert words.words.stop == {"en": ("x", "y")} and words.words.no == {}
    with pytest.raises(TypeError):
        words.words.stop["ar"] = ("z",)  # type: ignore[index]


def test_every_timing_or_size_setting_has_its_unit_in_its_name() -> None:
    """The design's 7.3: `_ms` or `_s`, `_mb` for a size, or the thing counted for a count
    (`_words`, `_tokens`, `_digits`, `_threads`, and the window a cap counts over, `_per_day`
    or `_per_turn`: the design's 7.6 names); only a ratio from 0 to 1 has none."""
    numbers = [loc for loc, kind in fields() if kind in (int, float)]
    units = (
        "_ms",
        "_s",
        "_mb",
        "_words",
        "_tokens",
        "_digits",
        "_threads",
        "_per_day",
        "_per_turn",
    )
    unnamed = [loc for loc in numbers if not loc[-1].endswith(units) and loc not in RATIOS]
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
