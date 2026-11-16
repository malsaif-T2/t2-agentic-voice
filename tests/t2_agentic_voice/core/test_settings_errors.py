"""How the settings fail (the design's 7.4), built in code or loaded with `from_env`: one
ConfigurationError naming each setting that cannot load under the prefix, with a FIX line, never
the value it rejected (GP-19), and chained to nothing; a group built on its own keeps pydantic's
ValidationError, its input hidden. Loading itself: test_config.py."""

from __future__ import annotations

import json
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
    ("encoding", "comment"),
    [("utf-16", "# the key\n"), ("utf-16-le", "# the key\n"), ("cp1252", "# café\n")],
)
def test_an_env_file_that_is_no_utf8_is_refused_never_showing_its_bytes(
    tmp_path: Path, encoding: str, comment: str
) -> None:
    """Windows PowerShell 5.1's `>` writes UTF-16, .NET's encoders may write it with no
    byte-order mark (every byte valid UTF-8, a NUL after each character, so every line would
    be dropped unseen), and an old editor cp1252: the decoder's error holds every byte of the
    file, the key among them, so it is neither raised nor chained; and the file is refused,
    `env` given in code or not."""
    dotenv = tmp_path / "other.env"
    dotenv.write_bytes(f"{comment}{PREFIX}GROQ__API_KEY={MADE_UP_KEY}\n".encode(encoding))
    loads: list[Callable[[], object]] = [
        lambda: VoiceSettings.from_env(env_file=dotenv),
        lambda: VoiceSettings.from_env(env_file=dotenv, env="test"),
    ]
    for load in loads:
        with pytest.raises(ConfigurationError) as raised:
            load()
        error = raised.value
        assert error.message == "The env file given is not UTF-8 text. FIX: save it as UTF-8 text."
        assert error.details == {"setting": "env_file"}
        assert (error.__cause__, error.__context__) == (None, None)
        for shown_value in (MADE_UP_KEY, MADE_UP_KEY.encode(encoding).hex(), str(tmp_path)):
            assert holding(shown_value, shown(error)) == []


def test_an_env_file_that_cannot_be_opened_says_to_check_it_not_to_save_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file another program holds open, or this user may not read, is an OSError, which no
    saving as UTF-8 fixes."""
    dotenv = tmp_path / "locked.env"
    dotenv.write_text(f"{PREFIX}GROQ__API_KEY={MADE_UP_KEY}\n", encoding="utf-8")
    read_bytes = Path.read_bytes

    def locked(path: Path) -> bytes:
        if path == dotenv:
            raise PermissionError(13, "Permission denied", str(path))
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", locked)
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env(env_file=dotenv)
    error = raised.value
    assert error.message.startswith(
        "The env file given cannot be read (PermissionError). FIX: check that the file exists "
        "and that this process may read it"
    )
    assert "UTF-8" not in error.message and error.details == {"setting": "env_file"}
    assert (error.__cause__, error.__context__) == (None, None)
    for shown_value in (MADE_UP_KEY, str(tmp_path)):
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


def test_a_value_that_is_not_json_is_named_with_every_other_failing_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list written as plain text, a common slip, no longer hides the load's other failures,
    a short secret among them: one load names them all, the secret shown nowhere."""
    short = "made-up-31-bytes-secret-0123456"
    monkeypatch.setenv(f"{PREFIX}SERVER__ALLOWED_ORIGINS", "https://ole5.example")
    monkeypatch.setenv(f"{PREFIX}SERVER__TURN_SECRET", short)
    monkeypatch.setenv(f"{PREFIX}GROQ__BASE_URL", "http://api.groq.com")
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.from_env()
    suffixes = ["SERVER__ALLOWED_ORIGINS", "GROQ__BASE_URL", "SERVER__TURN_SECRET"]
    assert _named(raised.value) == [f"{PREFIX}{each}" for each in suffixes]
    assert f"{PREFIX}SERVER__ALLOWED_ORIGINS (is not valid JSON)" in raised.value.message
    assert holding(short, shown(raised.value)) == []
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)


@pytest.mark.parametrize(
    "pattern",
    [
        "a{4294967296}",  # re raises OverflowError: past its repetition limit
        "(" * 3_000 + "x" + ")" * 3_000,  # RecursionError: nested past the parser's depth
        f"(?P<{MADE_UP_KEY}!>x)",  # re.error, whose text quotes the group's name
        f"(?P={MADE_UP_KEY})",
    ],
)
def test_a_redact_pattern_re_cannot_compile_is_named_with_the_rest_never_its_text(
    monkeypatch: pytest.MonkeyPatch, pattern: str
) -> None:
    """Every error `re.compile` raises is the settings' one ConfigurationError, naming the
    pattern by its place in the list with the load's other failures, never any of its text,
    loaded or built in code; an OverflowError or a RecursionError would have stopped the load
    raw, with no FIX line, and re.error's text would have shown part of the value."""
    monkeypatch.setenv(f"{PREFIX}TRACING__REDACT", json.dumps(["x", pattern]))
    monkeypatch.setenv(f"{PREFIX}GROQ__BASE_URL", "http://api.groq.com")
    data = {"env": "test", "groq": {"base_url": "http://api.groq.com"}}
    builds: list[Callable[[], object]] = [
        VoiceSettings.from_env,
        lambda: VoiceSettings.model_validate(data | {"tracing": {"redact": ("x", pattern)}}),
    ]
    for build in builds:
        with pytest.raises(ConfigurationError) as raised:
            build()
        error = raised.value
        assert _named(error) == [f"{PREFIX}GROQ__BASE_URL", f"{PREFIX}TRACING__REDACT"]
        why = "(Value error, pattern 1 is not a regular expression Python's re module compiles)"
        assert f"{PREFIX}TRACING__REDACT {why}" in error.message and "FIX:" in error.message
        assert holding(MADE_UP_KEY, shown(error)) == []
        assert (error.__cause__, error.__context__) == (None, None)


@pytest.mark.parametrize(
    "pattern",
    [
        "a{4294967296}",  # re raises OverflowError: past its repetition limit
        f"(?P={MADE_UP_KEY})",  # re.error, whose text quotes the group's name
    ],
)
def test_an_id_pattern_re_cannot_compile_is_named_never_its_text(
    monkeypatch: pytest.MonkeyPatch, pattern: str
) -> None:
    """The guard's ID patterns fail as the redact patterns do: an OverflowError stopped the
    load raw, with no setting named and no FIX line."""
    monkeypatch.setenv(f"{PREFIX}GUARD__ID_PATTERNS", json.dumps(["x", pattern]))
    builds: list[Callable[[], object]] = [
        VoiceSettings.from_env,
        lambda: VoiceSettings.model_validate(
            {"env": "test", "guard": {"id_patterns": ("x", pattern)}}
        ),
    ]
    for build in builds:
        with pytest.raises(ConfigurationError) as raised:
            build()
        error = raised.value
        assert _named(error) == [f"{PREFIX}GUARD__ID_PATTERNS"]
        why = "(Value error, pattern 1 is not a regular expression Python reads)"
        assert f"{PREFIX}GUARD__ID_PATTERNS {why}" in error.message and "FIX:" in error.message
        assert holding(MADE_UP_KEY, shown(error)) == []
        assert (error.__cause__, error.__context__) == (None, None)


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
        ("SESSION__MODE", "chat"),
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
    (("openai", "base_url"), f"https://user:{MADE_UP_KEY}@api.openai.com/v1"),
    (("speechmatics", "region"), MADE_UP_KEY),
    (("tracing", "endpoint"), f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
    (("server", "allowed_origins"), (f"https://{MADE_UP_KEY}.example/path",)),
    (("server", "allowed_origins"), (f"https://{MADE_UP_KEY}.example:443",)),
    (("server", "allowed_origins"), (f"https://example.com\\{MADE_UP_KEY}",)),  # a backslash
    (("server", "forwarded_allow_ips"), ("::ffff:0:0/100", MADE_UP_KEY)),
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
    assert holding(MADE_UP_KEY, shown(raised.value)) == ["errors", "errors json"]
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


@pytest.mark.parametrize(
    "text",
    [
        f'{{"env": "test", "groq": {{"api_key": "{MADE_UP_KEY}"}},}}',  # a trailing comma
        f'{{"env": "test", "groq": {{"api_key": "{MADE_UP_KEY}"',  # cut short
        f'{{"env": "test", "x": {"[" * 300}"{MADE_UP_KEY}"{"]" * 300}}}',  # past its depth
        f'{{"env": "test", "groq": {{"api_key": "{MADE_UP_KEY}"}}}}'.encode() + b"\xff",
        f'{{"env": "test", "groq": {{"api_key": "{MADE_UP_KEY}"}}}}'.encode("utf-16"),
        "",
    ],
)
def test_text_that_is_not_json_fails_as_every_other_load(text: str | bytes) -> None:
    """pydantic parses the text before any validator runs, and its error's `errors()` hold the
    whole text, the key among it; `model_validate_json` names "the settings" instead, in one
    ConfigurationError chained to nothing."""
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.model_validate_json(text)
    error = raised.value
    assert error.message == (
        "These settings cannot load: the settings (is not valid JSON). FIX: correct each one in "
        "the code that builds the settings."
    )
    assert holding(MADE_UP_KEY, shown(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)
    assert VoiceSettings.model_validate_json('{"env": "test"}') == VoiceSettings(env="test")


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
