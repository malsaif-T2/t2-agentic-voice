"""Settings: typed, prefixed, nested in groups, listed in .env.example, and every secret kept
out of every repr and log line (docs/SECURITY.md, invariant 5)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel, SecretStr, ValidationError
from t2_agentic_voice.core.config import GroqSettings, Settings, get_settings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import configure_logging, get_logger

from tests.leaks import holding, shown

ROOT = Path(__file__).resolve().parents[3]
PREFIX = Settings.model_config.get("env_prefix", "")
MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
SECRET_NAME = re.compile(r"(^|_)(key|secret|token|password)$")


def _keys(model: type[BaseModel], prefix: str) -> set[str]:
    """Every environment name of `model`'s fields, a group's nested with `__`."""
    keys: set[str] = set()
    for name, field in model.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            keys |= _keys(kind, f"{prefix}{name.upper()}__")
        else:
            keys.add(f"{prefix}{name.upper()}")
    return keys


def _fields(model: type[BaseModel], path: str = "") -> Iterator[tuple[str, object]]:
    """(dotted name, annotation) of every leaf field, through the groups."""
    for name, field in model.model_fields.items():
        kind = field.annotation
        if isinstance(kind, type) and issubclass(kind, BaseModel):
            yield from _fields(kind, f"{path}{name}.")
        else:
            yield f"{path}{name}", kind


def test_defaults_boot_without_a_dotenv() -> None:
    settings = Settings(_env_file=None)
    assert (settings.env, settings.log_level, settings.log_format) == ("dev", "INFO", "console")
    assert (settings.groq.api_key, settings.groq.base_url) == (None, "https://api.groq.com")
    assert (settings.stt.provider, settings.stt.model, settings.stt.timeout_s) == (
        "groq",
        "whisper-large-v3",
        6.0,
    )
    assert (settings.tracing.endpoint, settings.tracing.include_transcripts) == (None, True)


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}LOG_LEVEL", "DEBUG")
    assert Settings(_env_file=None).log_level == "DEBUG"


def test_reads_each_group_nested_with_two_underscores(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "GROQ__API_KEY": MADE_UP_KEY,
        "STT__MODEL": "whisper-large-v3-turbo",
        "STT__TIMEOUT_S": "4.5",
        "TRACING__ENDPOINT": "http://127.0.0.1:6006/v1/traces",
        "TRACING__INCLUDE_TRANSCRIPTS": "false",
        "TRACING__REDACT": '["\\\\d{10}"]',
    }.items():
        monkeypatch.setenv(f"{PREFIX}{name}", value)
    settings = Settings(_env_file=None)
    assert settings.groq.api_key is not None
    assert settings.groq.api_key.get_secret_value() == MADE_UP_KEY
    assert (settings.stt.model, settings.stt.timeout_s) == ("whisper-large-v3-turbo", 4.5)
    assert settings.tracing.endpoint == "http://127.0.0.1:6006/v1/traces"
    assert (settings.tracing.include_transcripts, settings.tracing.redact) == (False, (r"\d{10}",))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LOG_LEVEL", "LOUD"),
        ("STT__MODLE", "whisper-large-v3"),  # a misspelt key in a group
        ("STT__MODEL", "whisper-1"),
        ("STT__TIMEOUT_S", "0"),
        ("STT__TIMEOUT_S", "inf"),  # no limit at all
        ("GROQ__BASE_URL", "http://api.groq.com"),  # the key would travel in clear text
        ("GROQ__BASE_URL", "https://user:pw@api.groq.com"),
        ("GROQ__BASE_URL", "https://api.groq.com:notaport"),
        ("GROQ__BASE_URL", "https://api.groq.com:99999"),
        ("GROQ__BASE_URL", "https://api.groq.com:0"),
        ("GROQ__BASE_URL", "https://api.groq.com?x=1"),  # the SDK's path would follow the query
        ("GROQ__BASE_URL", "https://api.groq.com/#f"),
        ("TRACING__ENDPOINT", "localhost:6006"),
        ("TRACING__ENDPOINT", "http://127.0.0.1:6006x/v1/traces"),
        ("TRACING__REDACT", '["("]'),
    ],
)
def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GROQ__BASE_URL", f"https://user:{MADE_UP_KEY}@api.groq.com"),
        ("GROQ__BASE_URL", f"https://api.groq.com:{MADE_UP_KEY}"),  # urllib's text repeats it
        ("GROQ__BASE_URL", f"https://[{MADE_UP_KEY}]/"),
        ("GROQ__APIKEY", MADE_UP_KEY),  # a misspelt key in a group
        ("STT__MODEL", MADE_UP_KEY),  # the key pasted into the wrong setting
        ("TRACING__ENDPOINT", f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
    ],
)
def test_a_rejected_value_is_never_echoed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """GP-19: an error names the setting, never the value it rejected, which may be a key. Only
    in its text, repr and traceback: `errors()` and `json()` still return the value unless given
    `include_input=False` (pydantic's default), which is why commands load through `from_env`."""
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)
    assert name.lower().replace("__", ".") in str(raised.value)
    assert holding(MADE_UP_KEY, shown(raised.value)) == []
    assert MADE_UP_KEY not in raised.value.json(include_input=False)  # the messages too
    for line in raised.value.errors(include_input=False):  # nor urllib's text, chained unseen
        error = line.get("ctx", {}).get("error")
        assert error is None or error.__context__ is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GROQ__APIKEY", MADE_UP_KEY),
        ("GROQ__BASE_URL", f"https://user:{MADE_UP_KEY}@api.groq.com"),
        ("TRACING__ENDPOINT", f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
        ("STT__MODEL", MADE_UP_KEY),
    ],
)
def test_from_env_names_each_failing_setting_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """The design's 7.4: every failure is a ConfigurationError with a FIX line; and it leads to
    no ValidationError, whose `errors()` holds the value."""
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env()
    error = raised.value
    assert f"{PREFIX}{name}" in error.message and "FIX:" in error.message
    assert f"'setting': '{PREFIX}{name}'" in repr(error.details)
    assert holding(MADE_UP_KEY, shown(error)) == []
    assert (error.__cause__, error.__context__) == (None, None)


@pytest.mark.parametrize("name", sorted(_keys(Settings, PREFIX)))
def test_no_setting_shows_a_value_it_refuses(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GP-19 for every setting, one added later included: given the made-up key (pasted into
    the wrong setting), each setting takes it, or `from_env` refuses it without showing it."""
    monkeypatch.setenv(name, MADE_UP_KEY)
    try:
        Settings.from_env()
    except ConfigurationError as error:
        assert holding(MADE_UP_KEY, shown(error)) == []
        assert (error.__cause__, error.__context__) == (None, None)


def test_from_env_refuses_a_value_that_does_not_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JSON value cut short: the parser's own error would hold the whole value."""
    monkeypatch.setenv(f"{PREFIX}TRACING__REDACT", f'["{MADE_UP_KEY}"')
    with pytest.raises(ConfigurationError, match="cannot load") as raised:
        Settings.from_env()
    assert holding(MADE_UP_KEY, shown(raised.value)) == []
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)


def test_from_env_reads_the_environment_and_its_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / "run.env"
    dotenv.write_text(f"{PREFIX}STT__MODEL=whisper-large-v3-turbo\n", encoding="utf-8")
    monkeypatch.setenv(f"{PREFIX}LOG_LEVEL", "DEBUG")
    assert Settings.from_env().model_dump() == Settings(_env_file=None).model_dump()
    loaded = Settings.from_env(env_file=dotenv)
    assert (loaded.stt.model, loaded.log_level) == ("whisper-large-v3-turbo", "DEBUG")


@pytest.mark.parametrize("kind", ["a missing file", "a folder"])
def test_from_env_refuses_an_env_file_that_is_no_file(tmp_path: Path, kind: str) -> None:
    """pydantic-settings skips a missing env file silently: a mistyped `--env-file` would run
    on the defaults (GP-06)."""
    path = tmp_path / "missing.env" if kind == "a missing file" else tmp_path
    with pytest.raises(ConfigurationError, match="FIX:") as raised:
        Settings.from_env(env_file=path)
    assert raised.value.details == {"setting": "env_file"}
    assert holding(str(tmp_path), shown(raised.value)) == []


def test_a_blank_value_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank timeout would otherwise fail, and a blank key file would become the path `.`."""
    monkeypatch.setenv(f"{PREFIX}STT__TIMEOUT_S", "")
    monkeypatch.setenv(f"{PREFIX}GROQ__API_KEY_FILE", "")
    settings = Settings(_env_file=None)
    assert (settings.stt.timeout_s, settings.groq.api_key_file) == (6.0, None)


def test_the_providers_own_variables_change_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The design's 7.3: other names are never read."""
    monkeypatch.setenv("GROQ_API_KEY", MADE_UP_KEY)
    monkeypatch.setenv("GROQ_BASE_URL", "https://elsewhere.example")
    groq = Settings(_env_file=None).groq
    assert (groq.api_key, groq.resolved_api_key(), groq.base_url) == (
        None,
        None,
        "https://api.groq.com",
    )


def test_get_settings_is_loaded_once() -> None:
    """Under tests/conftest.py, it reads no `.env` and no variable from the shell."""
    assert get_settings() is get_settings()


def test_env_example_lists_every_setting() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    documented = {
        line.split("=", 1)[0].strip()
        for line in lines
        if "=" in line and not line.lstrip().startswith("#")
    }
    expected = _keys(Settings, PREFIX)
    assert documented == expected, (
        "Keep .env.example in sync with Settings in core/config.py: "
        f"missing={sorted(expected - documented)} unknown={sorted(documented - expected)}. "
        "FIX: add each missing key with a comment saying what it is; remove each unknown one."
    )


def test_env_example_as_a_dotenv_holds_the_defaults(tmp_path: Path) -> None:
    """`.env.example` says "Copy to `.env` and fill in": a copy with only the key filled in
    keeps every other setting at its default."""
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    defaults = Settings(_env_file=None).model_dump()
    assert Settings(_env_file=ROOT / ".env.example").model_dump() == defaults
    copy = tmp_path / ".env"
    key_line = f"{PREFIX}GROQ__API_KEY="
    assert key_line + "\n" in example
    copy.write_text(example.replace(key_line, key_line + MADE_UP_KEY), encoding="utf-8")
    filled = Settings(_env_file=copy)
    assert filled.groq.resolved_api_key() == SecretStr(MADE_UP_KEY)
    assert filled.model_dump() | {"groq": defaults["groq"]} == defaults


def test_the_key_comes_from_the_setting_or_its_file(tmp_path: Path) -> None:
    key_file = tmp_path / "groq.key"
    key_file.write_text(f"  {MADE_UP_KEY}\n", encoding="utf-8")
    empty = tmp_path / "empty.key"
    empty.write_text("\n", encoding="utf-8")
    assert GroqSettings(api_key=SecretStr(f" {MADE_UP_KEY} ")).resolved_api_key() == SecretStr(
        MADE_UP_KEY
    )
    from_file = GroqSettings(api_key=SecretStr("  "), api_key_file=key_file)
    assert from_file.resolved_api_key() == SecretStr(MADE_UP_KEY)
    assert GroqSettings(api_key_file=empty).resolved_api_key() is None
    assert GroqSettings().resolved_api_key() is None


def test_a_key_file_saved_with_a_byte_order_mark_gives_the_bare_key(tmp_path: Path) -> None:
    """Notepad's "UTF-8 with BOM", or Windows PowerShell 5.1's `Set-Content -Encoding UTF8`."""
    key_file = tmp_path / "groq.key"
    key_file.write_bytes(b"\xef\xbb\xbf" + MADE_UP_KEY.encode() + b"\r\n")
    assert GroqSettings(api_key_file=key_file).resolved_api_key() == SecretStr(MADE_UP_KEY)


@pytest.mark.parametrize("kind", ["a folder", "a missing file", "an undecodable file"])
def test_an_unreadable_key_file_names_the_setting_never_its_contents(
    tmp_path: Path, kind: str
) -> None:
    path = {"a folder": tmp_path, "a missing file": tmp_path / "nope.key"}.get(
        kind, tmp_path / "bad.key"
    )
    if kind == "an undecodable file":
        path.write_bytes(b"\xff" + MADE_UP_KEY.encode())
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key_file=path).resolved_api_key()
    assert f"{PREFIX}GROQ__API_KEY_FILE" in raised.value.message
    assert holding(MADE_UP_KEY, shown(raised.value)) == []
    assert holding(str(path), shown(raised.value)) == []
    # Not even out of sight: a decode error holds the file's bytes, the key with them.
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)


@pytest.mark.parametrize(
    "contents",
    [
        f"{MADE_UP_KEY}\n# the eval key\n",  # a second line: a comment
        f"{MADE_UP_KEY}\r\n# the eval key\r\n",
        f"gsk_made up {MADE_UP_KEY}",  # a space inside
        f"gsk_made\t{MADE_UP_KEY}",
        f"{MADE_UP_KEY}\u200b",  # a zero-width space, pasted with it
    ],
)
def test_a_key_file_holding_more_than_the_key_is_refused(tmp_path: Path, contents: str) -> None:
    """Such a key fails in the HTTP client, whose error holds the whole header, and reads as a
    lost connection that is asked again; so it is refused as it is read."""
    key_file = tmp_path / "groq.key"
    key_file.write_text(contents, encoding="utf-8", newline="")
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key_file=key_file).resolved_api_key()
    assert raised.value.details == {"setting": f"{PREFIX}GROQ__API_KEY_FILE"}
    assert holding(MADE_UP_KEY, shown(raised.value)) == []


@pytest.mark.parametrize(
    "key", [f"{MADE_UP_KEY}\rx", f"{MADE_UP_KEY}\nx", f"{MADE_UP_KEY}\x00x", f"\u200b{MADE_UP_KEY}"]
)
def test_a_key_with_a_character_no_key_holds_is_refused(key: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key=SecretStr(key)).resolved_api_key()
    assert raised.value.details == {"setting": f"{PREFIX}GROQ__API_KEY"}
    assert holding(MADE_UP_KEY, shown(raised.value)) == []


def test_every_secret_setting_is_a_secret_str() -> None:
    secrets = [(name, kind) for name, kind in _fields(Settings) if SECRET_NAME.search(name)]
    assert [name for name, _ in secrets] == ["groq.api_key"]
    assert all(kind in (SecretStr, SecretStr | None) for _, kind in secrets), secrets


def test_a_key_appears_in_no_repr_and_no_log_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    key_file = tmp_path / "groq.key"
    key_file.write_text(MADE_UP_KEY, encoding="utf-8")
    settings = Settings(_env_file=None, groq=GroqSettings(api_key=SecretStr(MADE_UP_KEY)))
    from_file = Settings(_env_file=None, groq=GroqSettings(api_key_file=key_file))
    configure_logging("DEBUG", "json")  # tests/conftest.py puts the defaults back
    log = get_logger("tests.config")
    for each in (settings, from_file):
        log.info("settings_read", settings=each, groq=each.groq)
        log.info("key_read", key=each.groq.resolved_api_key())
        logging.getLogger("some.library").warning("settings %s %r", each, each.groq)
    surfaces = shown(caplog=caplog, capsys=capsys)
    for index, each in enumerate((settings, from_file)):
        key = each.groq.resolved_api_key()
        texts = [repr(each), str(each), each.model_dump_json(), repr(each.model_dump())]
        surfaces[f"settings {index}"] = "\n".join([*texts, repr(key), str(key)])
    assert surfaces["stdout"].count("settings_read") == 2
    assert holding(MADE_UP_KEY, surfaces) == []
