"""What the settings groups share: the base of a group, how a setting's environment name is
made, and the checks several groups' values take (a URL; a key's characters; a shared secret's
least length; a secret given as a file).

Every error names the setting and never the value it rejected, which may be a key pasted into
the wrong setting (GP-19). A group's checks name a setting under the prefix the settings were
loaded with, which `VoiceSettings.from_env` passes down as the validation context
(`{"prefix": ...}`); built in code, under the library's own, `T2V_`.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationInfo

from t2_agentic_voice.core.errors import ConfigurationError

# The library's own prefix (the design's 7.3; open question 4): `from_env(prefix=...)` picks
# another.
PREFIX = "T2V_"
# What a group's fields nest with in a name: `T2V_GROQ__API_KEY` is `settings.groq.api_key`.
NESTED = "__"
# What an API key or a shared secret may hold: printable ASCII with no space, as an HTTP header
# carries it.
_KEY = re.compile(r"[\x21-\x7e]+")
# The fewest bytes a join key or the TURN secret holds: an HS256 key is at least as long as its
# hash's output (RFC 7518, 3.2), and the TURN secret signs with HMAC too.
MIN_SECRET_BYTES = 32
# The command a FIX line gives for a new secret: 48 random bytes, 64 URL-safe characters.
GENERATOR = 'python -c "import secrets; print(secrets.token_urlsafe(48))"'


def setting_name(*location: str | int, prefix: str = PREFIX) -> str:
    """The environment name of the setting at `location`, a group's name then its field's, as
    a pydantic error's `loc` gives it: `T2V_GROQ__API_KEY` for ("groq", "api_key"). An item's
    index in a list setting is left out, since the name is the whole setting's."""
    return prefix + NESTED.join(str(part).upper() for part in location if isinstance(part, str))


def prefix_of(info: ValidationInfo) -> str:
    """The prefix the settings are being loaded under: `from_env`'s, or the library's own."""
    context = info.context if isinstance(info.context, dict) else {}
    prefix = context.get("prefix", PREFIX)
    return prefix if isinstance(prefix, str) else PREFIX


class Group(BaseModel):
    """A group of settings: read-only once loaded, and a misspelt key in it is an error. An
    error's text and repr name the setting, never the value it rejected, which may be a key
    (GP-19). A ValidationError's `errors()` and `json()` still return that value unless given
    `include_input=False`, so a command reports settings errors only through
    `VoiceSettings.from_env`, never from a ValidationError itself."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


def url(value: str, schemes: frozenset[str]) -> str:
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


def key(value: str, setting: str) -> SecretStr:
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


def secret(value: str, setting: str) -> SecretStr:
    """`value` as a shared secret (a join key, the TURN secret): a key's characters, and at least
    `MIN_SECRET_BYTES` bytes; or ConfigurationError naming `setting`, never the value, whose FIX
    line gives a command that makes one."""
    checked = key(value, setting)
    if len(value.encode("utf-8")) < MIN_SECRET_BYTES:
        raise ConfigurationError(
            f"{setting} holds a secret shorter than {MIN_SECRET_BYTES} bytes. FIX: make a new "
            f"one with {GENERATOR}",
            details={"setting": setting},
        )
    return checked


def read_secret_file(path: Path, setting: str) -> str | None:
    """The contents of the secret file `path` (a byte-order mark dropped, as Notepad and Windows
    PowerShell 5.1 may write one), with the space around them removed; None when it holds
    nothing. A file that cannot be read raises ConfigurationError naming `setting`, never the
    file's path or its bytes."""
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError) as error:
        failure = type(error).__name__  # a decode error holds the file's bytes: not chained
    else:
        return text or None
    raise ConfigurationError(
        f"{setting} is set, but the file cannot be read ({failure}).",
        details={"setting": setting},
    )
