"""Application settings: the only module that reads the environment (ARCH-ENV).

Every configurable value is a field on `Settings`, loaded from environment variables with this
project's prefix, or from a local `.env` file (environment variables win). A group of settings
nests with `__`: `T2V_GROQ__API_KEY` is `settings.groq.api_key`. A blank value counts as unset,
so a `.env` copied from `.env.example` with only the key filled in keeps every other default.
Other modules call `get_settings()` or receive a `Settings` instance; they never touch
`os.environ`. No provider's own variable (`GROQ_API_KEY`, `OTEL_*`) is ever read here, and the
adapters pass every value that keeps their SDKs from reading one (the design's 7.3). The few an
SDK reads whatever is passed (`GROQ_CUSTOM_HEADERS`, `GROQ_LOG`, some `OTEL_*`) are listed in
plan 002's decision log, each kept out by the track that builds its adapter or left as debt.
A command loads the settings with `Settings.from_env`, whose ConfigurationError names each
setting that cannot load and never the value it rejected (the design's 7.4).

When you add a field, add it to `.env.example` too (tests/t2_agentic_voice/core/test_config.py
fails otherwise).
A secret is a `SecretStr` field, so it never shows in a repr or a log; one may also be given as
a file whose contents are the value (`api_key_file`).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from t2_agentic_voice.core.errors import ConfigurationError

PREFIX = "T2V_"
Environment = Literal["dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]
SttProvider = Literal["groq"]
SttModel = Literal["whisper-large-v3", "whisper-large-v3-turbo"]
# What an API key may hold: printable ASCII with no space, as an HTTP header carries it.
_KEY = re.compile(r"[\x21-\x7e]+")


def _url(value: str, schemes: frozenset[str]) -> str:
    """A URL of one of `schemes`, with a host, a port from 1 to 65535 if any, and no user name or
    password in it. Every error is fixed text: urllib's own repeats the value, which may be a
    key pasted into the wrong setting."""
    parts = _split(value)
    if (
        parts is None
        or parts.scheme not in schemes
        or not parts.hostname
        or parts.port == 0
        or any(c.isspace() for c in value)
    ):
        raise ValueError(f"must be a URL starting with {' or '.join(sorted(schemes))}://")
    if parts.username is not None or parts.password is not None:
        raise ValueError("must not hold a user name or password; secrets go in their own setting")
    return value


def _split(value: str) -> SplitResult | None:
    """`value`'s parts, or None when urllib refuses it, so its error, which repeats the value,
    is in no exception chain either."""
    try:
        parts = urlsplit(value)  # refuses an invalid [host]
        _ = parts.port  # urlsplit checks the port only when it is read
    except ValueError:
        return None
    return parts


def _key(value: str, setting: str) -> SecretStr:
    """`value` as a key, or ConfigurationError naming `setting`, never the value: a key with a
    line break, a space, a control or a non-ASCII character inside it fails in the HTTP client,
    whose error holds the whole header (the key with it) and reads as a lost connection."""
    if not _KEY.fullmatch(value):
        raise ConfigurationError(
            f"{setting} holds a character no API key holds: a space or a line break inside it, "
            "or a control or non-ASCII character. FIX: give the key alone, on one line.",
            details={"setting": setting},
        )
    return SecretStr(value)


class _Group(BaseModel):
    """A group of settings: read-only once loaded, and a misspelt key in it is an error. An
    error's text and repr name the setting, never the value it rejected, which may be a key
    (GP-19). A ValidationError's `errors()` and `json()` still return that value unless given
    `include_input=False`, so a command reports settings errors only through `Settings.from_env`,
    never from a ValidationError itself."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class GroqSettings(_Group):
    """Groq, the provider of every model for now (D-004): `T2V_GROQ__*`."""

    # The API key, required by the Groq adapters; or give `api_key_file` instead.
    api_key: SecretStr | None = None
    # A file whose contents are the key, so the key can live outside `.env`.
    api_key_file: Path | None = None
    # The API's address: the SDK's own default, always passed to it, so the SDK never falls
    # back to GROQ_BASE_URL. HTTPS only, since the key travels with every request.
    base_url: str = "https://api.groq.com"

    @field_validator("base_url")
    @classmethod
    def _https(cls, value: str) -> str:
        parts = urlsplit(_url(value, frozenset({"https"})))
        if parts.query or parts.fragment:
            raise ValueError("must hold no query or fragment: the SDK adds its own path after it")
        return value

    def resolved_api_key(self) -> SecretStr | None:
        """The key: `api_key` when set, otherwise the contents of `api_key_file` (a byte-order
        mark dropped, as Notepad and Windows PowerShell 5.1 may write one), with the space around
        them removed; None when neither holds one (a blank value counts as unset). A key file
        that cannot be read, or a key holding a character no key holds, raises
        ConfigurationError naming the setting it came from, never its value or the file's path."""
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            return _key(self.api_key.get_secret_value().strip(), f"{PREFIX}GROQ__API_KEY")
        if self.api_key_file is None:
            return None
        setting = f"{PREFIX}GROQ__API_KEY_FILE"
        try:
            text = self.api_key_file.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeDecodeError) as error:
            failure = type(error).__name__  # a decode error holds the file's bytes: not chained
        else:
            return _key(text, setting) if text else None
        raise ConfigurationError(
            f"{setting} is set, but the file cannot be read ({failure}).",
            details={"setting": setting},
        )


class SttSettings(_Group):
    """Speech-to-text: `T2V_STT__*`."""

    # Which adapter turns speech into text; only Groq's exists for now (D-004).
    provider: SttProvider = "groq"
    # The Whisper model. The default is set by plan 002's registered baseline (the design's 7.6).
    model: SttModel = "whisper-large-v3"
    # The longest one transcription request may take, in seconds, before it is a timeout.
    timeout_s: float = Field(default=6.0, gt=0, allow_inf_nan=False)


class TracingSettings(_Group):
    """Tracing, as plain OTLP to Phoenix or any OpenTelemetry backend (D-023): `T2V_TRACING__*`."""

    # Where spans are sent: an OTLP/HTTP traces endpoint, such as a local Phoenix's
    # http://127.0.0.1:6006/v1/traces. Unset: no span leaves the process, unless the app passes
    # its own tracer provider.
    endpoint: str | None = None
    # The project the spans are filed under in Phoenix. Unset: the backend's default.
    project: str | None = None
    # Whether spans carry what was said. Transcripts are the only call content a trace holds
    # (docs/SECURITY.md, invariant 8).
    include_transcripts: bool = True
    # Regular expressions; every match is replaced in each text attribute before it is
    # exported. A JSON list in the environment: T2V_TRACING__REDACT='["\\d{10}"]'.
    redact: tuple[str, ...] = ()

    @field_validator("endpoint")
    @classmethod
    def _http(cls, value: str | None) -> str | None:
        return None if value is None else _url(value, frozenset({"http", "https"}))

    @field_validator("redact")
    @classmethod
    def _patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, pattern in enumerate(value):
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"pattern {index} is not a regular expression: {error}") from None
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    env: Environment = "dev"
    log_level: LogLevel = "INFO"
    # console (human-readable) or json (machine-queryable)
    log_format: LogFormat = "console"
    # Local runtime data (git-ignored): databases, run outputs, caches. Every path under it
    # comes from here, so one setting moves a whole run, a test session included.
    var_dir: Path = Path("var")
    groq: GroqSettings = Field(default_factory=GroqSettings)
    stt: SttSettings = Field(default_factory=SttSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        """The settings from the environment and a `.env`: `env_file`, or `Settings`' own
        default when None. An `env_file` given that is no file is a ConfigurationError, since
        pydantic-settings skips a missing one silently and a mistyped path would run on the
        defaults (GP-06). Any setting that cannot load is a ConfigurationError naming each one
        (`T2V_GROQ__BASE_URL`) and why, with a FIX line, never the value it rejected (the
        design's 7.4). It is raised after the handler, so no exception chain leads back to the
        ValidationError, whose `errors()` would still return that value."""
        if env_file is not None and not env_file.expanduser().is_file():
            raise ConfigurationError(
                "The env file given cannot be read. FIX: pass the path of an existing .env file.",
                details={"setting": "env_file"},
            )
        problems: list[tuple[str, str]] = []
        try:
            return cls() if env_file is None else cls(_env_file=env_file)
        except ValidationError as error:
            for problem in error.errors(include_input=False, include_url=False):
                parts = [str(p).upper() for p in problem["loc"] if isinstance(p, str)]
                problems.append((PREFIX + "__".join(parts), problem["msg"]))
        except SettingsError as error:  # a JSON value that does not parse
            problems.append((f"{PREFIX}*", str(error)))
        raise ConfigurationError(
            "These settings cannot load: "
            + "; ".join(f"{name} ({why})" for name, why in problems)
            + ". FIX: correct each one in the environment or the .env file; .env.example lists "
            "every setting.",
            details={"settings": [{"setting": name, "problem": why} for name, why in problems]},
        )


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings, loaded once with `Settings.from_env`. Tests construct `Settings`
    directly instead."""
    return Settings.from_env()
