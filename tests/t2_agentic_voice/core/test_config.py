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
        ("GROQ__BASE_URL", "http://api.groq.com"),  # the key would travel in clear text
        ("GROQ__BASE_URL", "https://user:pw@api.groq.com"),
        ("TRACING__ENDPOINT", "localhost:6006"),
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
        ("STT__MODEL", MADE_UP_KEY),  # the key pasted into the wrong setting
        ("TRACING__ENDPOINT", f"https://user:{MADE_UP_KEY}@127.0.0.1:6006/v1/traces"),
    ],
)
def test_a_rejected_value_is_never_echoed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """GP-19: an error names the setting, never the value it rejected, which may be a key."""
    monkeypatch.setenv(f"{PREFIX}{name}", value)
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)
    assert name.lower().replace("__", ".") in str(raised.value)
    assert MADE_UP_KEY not in str(raised.value)
    assert MADE_UP_KEY not in repr(raised.value.errors(include_input=False))


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


def test_an_unreadable_key_file_names_the_setting_never_its_contents(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqSettings(api_key_file=tmp_path).resolved_api_key()  # a folder, not a file
    assert f"{PREFIX}GROQ__API_KEY_FILE" in raised.value.message
    assert str(tmp_path) not in raised.value.message


def test_every_secret_setting_is_a_secret_str() -> None:
    secrets = [(name, kind) for name, kind in _fields(Settings) if SECRET_NAME.search(name)]
    assert [name for name, _ in secrets] == ["groq.api_key"]
    assert all(kind in (SecretStr, SecretStr | None) for _, kind in secrets), secrets


def test_a_key_appears_in_no_repr_and_no_log_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key_file = tmp_path / "groq.key"
    key_file.write_text(MADE_UP_KEY, encoding="utf-8")
    settings = Settings(_env_file=None, groq=GroqSettings(api_key=SecretStr(MADE_UP_KEY)))
    from_file = Settings(_env_file=None, groq=GroqSettings(api_key_file=key_file))
    try:
        configure_logging("DEBUG", "json")
        log = get_logger("tests.config")
        for each in (settings, from_file):
            log.info("settings_read", settings=each, groq=each.groq)
            log.info("key_read", key=each.groq.resolved_api_key())
            logging.getLogger("some.library").warning("settings %s %r", each, each.groq)
    finally:
        configure_logging()
    shown = [capsys.readouterr().out]
    for each in (settings, from_file):
        shown += [repr(each), str(each), each.model_dump_json(), repr(each.model_dump())]
        shown += [repr(each.groq.resolved_api_key()), str(each.groq.resolved_api_key())]
    assert shown[0].count("settings_read") == 2
    assert [text for text in shown if MADE_UP_KEY in text] == []
