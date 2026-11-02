"""How the settings fail (the design's 7.4), built in code or loaded with `from_env`: one
ConfigurationError naming each setting that cannot load under the prefix, with a FIX line, never
the value it rejected (GP-19), and chained to nothing; a group built on its own keeps pydantic's
ValidationError, its input hidden. Loading itself: test_config.py."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import setting_name

from tests.leaks import holding, shown
from tests.t2_agentic_voice.core.settings_support import MADE_UP_KEY, PREFIX, names


def _named(error: ConfigurationError) -> list[object]:
    """The settings a ConfigurationError of several names, in order, from its details."""
    found = error.details["settings"]
    assert isinstance(found, list)
    return [each["setting"] for each in found if isinstance(each, dict)]


@pytest.fixture(autouse=True)
def _env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """`env` has no default: every load here gives one."""
    monkeypatch.setenv(f"{PREFIX}ENV", "test")


@pytest.mark.parametrize(
    ("encoding", "comment"), [("utf-16", "# the key\n"), ("cp1252", "# café\n")]
)
def test_an_env_file_that_is_no_utf8_is_refused_never_showing_its_bytes(
    tmp_path: Path, encoding: str, comment: str
) -> None:
    """Windows PowerShell 5.1's `>` writes UTF-16, and an old editor cp1252: the decoder's error
    holds every byte of the file, the key among them, so it is neither raised nor chained."""
    dotenv = tmp_path / "other.env"
    dotenv.write_bytes(f"{comment}{PREFIX}GROQ__API_KEY={MADE_UP_KEY}\n".encode(encoding))
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env(env_file=dotenv)
    error = raised.value
    assert error.message == (
        "The env file given cannot be read (UnicodeDecodeError). FIX: save it as UTF-8 text."
    )
    assert error.details == {"setting": "env_file"}
    assert (error.__cause__, error.__context__) == (None, None)
    for shown_value in (MADE_UP_KEY, MADE_UP_KEY.encode(encoding).hex(), str(tmp_path)):
        assert holding(shown_value, shown(error)) == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GROQ__BASE_URL", f"https://user:{MADE_UP_KEY}@api.groq.com"),
        ("GROQ__BASE_URL", f"https://api.groq.com:{MADE_UP_KEY}"),  # urllib's text repeats it
        ("GROQ__BASE_URL", f"https://[{MADE_UP_KEY}]/"),
        ("STT__MODEL", MADE_UP_KEY),  # the key pasted into the wrong setting
        ("TRACING__ENDPOINT", f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
        ("TRACING__REDACT", f'["{MADE_UP_KEY}"'),  # JSON cut short: its decoder quotes it
        ("JOIN__KEYS", f'{{"{MADE_UP_KEY}!": "{MADE_UP_KEY}"}}'),  # a key ID that is no ID
        ("SERVER__FORWARDED_ALLOW_IPS", f'["{MADE_UP_KEY}"]'),  # ipaddress's text repeats it
    ],
)
def test_from_env_names_each_failing_setting_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """The design's 7.4: every failure is a ConfigurationError with a FIX line, naming the
    setting whole (never a map's key below it); and it leads to no ValidationError, whose
    `errors()` holds the value."""
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    error = raised.value
    assert f"{PREFIX}{name} (" in error.message and "FIX:" in error.message
    assert f"'setting': '{PREFIX}{name}'" in repr(error.details)
    assert holding(MADE_UP_KEY, shown(error)) == []
    assert holding(MADE_UP_KEY.upper(), shown(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)


def test_a_json_value_nested_past_the_decoders_depth_is_not_valid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """json's RecursionError would otherwise escape from_env raw, with no FIX line."""
    monkeypatch.setenv(f"{PREFIX}SERVER__ALLOWED_ORIGINS", "[" * 5_000 + "]" * 5_000)
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert f"{PREFIX}SERVER__ALLOWED_ORIGINS (is not valid JSON)" in raised.value.message
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)


def test_from_env_says_what_to_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """An installed library ships no `.env.example`, so the FIX line names only the setting."""
    monkeypatch.setenv(f"{PREFIX}STT__TIMEOUT_S", "0")
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    assert raised.value.message == (
        f"These settings cannot load: {PREFIX}STT__TIMEOUT_S (Input should be greater than 0). "
        "FIX: correct each one in the environment, the .env file or the code values given."
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LOGGING__LEVEL", "LOUD"),
        ("STT__MODEL", "whisper-1"),
        ("STT__TIMEOUT_S", "inf"),  # no limit at all
        ("STT__LIVE_LANGUAGE", "ar"),
        ("GROQ__BASE_URL", "http://api.groq.com"),  # the key would travel in clear text
        ("GROQ__BASE_URL", "https://api.groq.com:notaport"),
        ("GROQ__BASE_URL", "https://api.groq.com:99999"),
        ("GROQ__BASE_URL", "https://api.groq.com:0"),
        ("GROQ__BASE_URL", "https://api.groq.com?x=1"),  # the SDK's path would follow the query
        ("GROQ__BASE_URL", "https://api.groq.com/#f"),
        ("TRACING__ENDPOINT", "localhost:6006"),
        ("TRACING__ENDPOINT", "http://127.0.0.1:6006x/v1/traces"),
        ("TRACING__REDACT", '["("]'),
        ("SESSION__MODE", "talker"),
        ("LOGGING__PIPECAT", "forward"),  # off only, for now (plan 003, Q19)
    ],
)
def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ConfigurationError, match=f"{PREFIX}{name} "):
        VoiceSettings.from_env()


@pytest.mark.parametrize("name", sorted(names()))
def test_no_setting_shows_a_value_it_refuses(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    recwarn: pytest.WarningsRecorder,
) -> None:
    """GP-19 for every setting, one added later included: given the made-up key (pasted into
    the wrong setting), each setting takes it, or `from_env` refuses it; either way nothing
    shows it, in the error, a log line, an output or a warning."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv(name, MADE_UP_KEY)
    refused: ConfigurationError | None = None
    try:
        VoiceSettings.from_env()
    except ConfigurationError as error:
        refused = error
        assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(refused, caplog=caplog, capsys=capsys, recwarn=recwarn)
    assert holding(MADE_UP_KEY, surfaces) == []


REFUSED_IN_CODE = [
    (("groq", "base_url"), f"https://user:{MADE_UP_KEY}@api.groq.com"),
    (("stt", "model"), MADE_UP_KEY),
    (("tracing", "endpoint"), f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
    (("server", "allowed_origins"), (f"https://{MADE_UP_KEY}.example/path",)),
    (("server", "allowed_origins"), (f"https://{MADE_UP_KEY}.example:443",)),
    (("server", "ice_servers"), (f"turn:user:{MADE_UP_KEY}@turn.example",)),
    (("server", "forwarded_allow_ips"), (f"{MADE_UP_KEY}/24",)),
    (("privacy", "consent_version"), f"{MADE_UP_KEY} with a space"),
]


@pytest.mark.parametrize(("location", "value"), REFUSED_IN_CODE)
def test_a_value_refused_in_code_is_never_echoed(location: tuple[str, str], value: object) -> None:
    """GP-19 and the design's 7.4 when the settings are built in code: one ConfigurationError
    naming the setting under the library's prefix, with a FIX line, never the value, and
    chained to nothing."""
    group, field = location
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.model_validate({"env": "test", group: {field: value}})
    error = raised.value
    assert f"{setting_name(group, field)} (" in error.message
    assert error.message.endswith("FIX: correct each one in the code that builds the settings.")
    assert holding(MADE_UP_KEY, shown(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)


@pytest.mark.parametrize(("location", "value"), REFUSED_IN_CODE)
def test_a_group_built_alone_keeps_the_validation_error_and_never_echoes(
    location: tuple[str, str], value: object
) -> None:
    """A group built on its own raises pydantic's ValidationError, whose text, repr and
    traceback name the setting, never the value. Its `errors()` and `json()` still return it
    unless given `include_input=False` (pydantic's default), so commands report through
    `VoiceSettings`."""
    group, field = location
    kind = VoiceSettings.model_fields[group].annotation
    assert isinstance(kind, type) and issubclass(kind, BaseModel)
    with pytest.raises(ValidationError) as raised:
        kind.model_validate({field: value})
    assert field in str(raised.value)
    assert holding(MADE_UP_KEY, shown(raised.value)) == []
    assert MADE_UP_KEY not in raised.value.json(include_input=False)  # the messages too
    for line in raised.value.errors(include_input=False):  # nor a library's text, chained unseen
        error = line.get("ctx", {}).get("error")
        assert error is None or error.__context__ is None


def test_settings_built_in_code_fail_as_from_env_does() -> None:
    """The constructor, `model_validate` and `model_validate_json` each raise one
    ConfigurationError naming every failing setting, under the library's prefix or the one the
    validation context gives, with what `from_env`'s details hold."""
    env = "-".join(("made", "up", "env"))  # built, so no traceback's source line shows it
    builds: list[Callable[[], object]] = [
        lambda: VoiceSettings(env=env, stt={"timeout_s": 0}),  # type: ignore[arg-type]
        lambda: VoiceSettings.model_validate({"env": env, "stt": {"timeout_s": 0}}),
        lambda: VoiceSettings.model_validate_json(f'{{"env": "{env}", "stt": {{"timeout_s": 0}}}}'),
    ]
    for build in builds:
        with pytest.raises(ConfigurationError) as raised:
            build()
        assert _named(raised.value) == [f"{PREFIX}ENV", f"{PREFIX}STT__TIMEOUT_S"]
        assert raised.value.code == "configuration_error"
        assert holding(env, shown(raised.value)) == []
        assert (raised.value.__cause__, raised.value.__context__) == (None, None)
    with pytest.raises(ConfigurationError, match="HELPDESK_VOICE_STT__TIMEOUT_S"):
        VoiceSettings.model_validate(
            {"env": "test", "stt": {"timeout_s": 0}}, context={"prefix": "HELPDESK_VOICE_"}
        )
    with pytest.raises(ConfigurationError, match=r"cannot load: the settings \(Input should"):
        VoiceSettings.model_validate(["not", "a", "mapping"])


def test_from_env_names_every_failing_setting_a_short_secret_among_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short join key or TURN secret no longer stops the load at the first failure: it is
    named with every other, and its secret is shown nowhere."""
    short = "made-up-31-bytes-secret-0123456"
    monkeypatch.setenv(f"{PREFIX}JOIN__KEYS", f'{{"k1": "{short}"}}')
    monkeypatch.setenv(f"{PREFIX}SERVER__TURN_SECRET", short)
    monkeypatch.setenv(f"{PREFIX}GROQ__BASE_URL", "http://api.groq.com")
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    suffixes = ["GROQ__BASE_URL", "SERVER__TURN_SECRET", "JOIN__KEYS"]
    assert _named(raised.value) == [f"{PREFIX}{each}" for each in suffixes]
    assert holding(short, shown(raised.value)) == []
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)
