"""What the settings groups share: the base of a group and of the settings, how a setting's
environment name is made, the checks several groups' values take (a URL; a key's characters; a
shared secret's least length; a secret given as a file), and the read-only form of a map
setting.

Every error names the setting and never the value it rejected, which may be a key pasted into
the wrong setting (GP-19). A group's checks raise ValueError with fixed text, which pydantic
collects with every other failure of the same load, and `VoiceSettings` turns them all into one
ConfigurationError naming each setting under the prefix the settings were loaded with
(`VoiceSettings.from_env` passes it down as the validation context, `{"prefix": ...}`; built
in code, the library's own, `T2V_`). A check made outside validation, as a secret file is
resolved, raises ConfigurationError itself. Assigning to built settings, or deleting a field,
raises a TypeError of fixed text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from urllib.parse import SplitResult, urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    SecretStr,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    WrapSerializer,
)

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
# The FIX lines for a file the settings read (a secret's, the `.env` given) that cannot be used:
# its text is not UTF-8, or the file cannot be opened or read at all.
NOT_UTF8 = "FIX: save it as UTF-8 text."
UNREADABLE = (
    "FIX: check that the file exists and that this process may read it: its permissions, or "
    "another program holding it open."
)


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


class ReadOnlyModel(BaseModel):
    """Settings nothing can change once built, `VoiceSettings` and each group: assigning to a
    field, or deleting any attribute, raises a TypeError naming it, never the value, where
    pydantic's own frozen error would show the value assigned, a key among them. A private
    attribute (`VoiceSettings`' prefix, which `from_env` sets) is pydantic's to set."""

    def __setattr__(self, name: str, value: object) -> None:
        if name not in self.__private_attributes__:
            raise _read_only(self, name)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        raise _read_only(self, name)


def _read_only(model: BaseModel, name: str) -> TypeError:
    """The error for a change to the field `name` of built settings, in fixed words."""
    return TypeError(
        f"{type(model).__name__}.{name} cannot change: settings are read-only once built. FIX: "
        "build new settings that hold the value, with VoiceSettings(...) or from_env(...)."
    )


class Group(ReadOnlyModel):
    """A group of settings: read-only once loaded, a map setting included (`FROZEN`), and a
    misspelt key in it is an error. A group object given to `VoiceSettings`, one made with
    `model_copy(update=...)` included, is validated again (`revalidate_instances`), so every
    check runs on it and its maps are read-only. Inside `VoiceSettings` its failures become the
    settings' one ConfigurationError. A group built on its own (`JoinSettings(...)`) raises
    pydantic's ValidationError instead, whose text and repr name the setting, never the value it
    rejected, which may be a key (GP-19); its `errors()` and `json()` still return that value
    unless given `include_input=False`, so a command reports settings errors only through
    `VoiceSettings`, never from a group's ValidationError itself."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", hide_input_in_errors=True, revalidate_instances="always"
    )


class ReadOnlyMap[K, V](Mapping[K, V]):
    """A map nothing can change once built, its entries behind a `MappingProxyType`. It copies,
    deep-copies and pickles through the plain map it holds, so settings that hold one still do,
    which a `MappingProxyType` alone cannot; and it hashes as its entries do when its values
    hash, two equal maps alike, so a frozen group that holds one hashes too."""

    __slots__ = ("_items",)

    def __init__(self, items: Mapping[K, V]) -> None:
        self._items: Mapping[K, V] = MappingProxyType(dict(items))

    def __getitem__(self, key: K) -> V:
        return self._items[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self._items)!r})"

    def __hash__(self) -> int:
        return hash(frozenset(self._items.items()))

    def __reduce__(self) -> tuple[type[ReadOnlyMap[K, V]], tuple[dict[K, V]]]:
        return type(self), (dict(self._items),)


def read_only[K, V](value: Mapping[K, V]) -> Mapping[K, V]:
    """`value` as a map nothing can change, so code that holds the settings cannot add an entry
    no check saw (a join key under 32 bytes) or change one every call shares (a voice)."""
    return ReadOnlyMap(value)


def plain(value: Mapping[object, object], dump: SerializerFunctionWrapHandler) -> object:
    """A read-only map dumped as the plain object it was given as."""
    return dump(dict(value))


# What a map setting's annotation adds, both together, with `validate_default=True` so its
# default is read-only too: `Annotated[Mapping[K, V], FROZEN, PLAIN]`.
FROZEN = AfterValidator(read_only)
PLAIN = WrapSerializer(plain)


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
    return _checked(value, setting, least=0)


def secret(value: str, setting: str) -> SecretStr:
    """`value` as a shared secret (a join key, the TURN secret): a key's characters, and at least
    `MIN_SECRET_BYTES` bytes; or ConfigurationError naming `setting`, never the value, whose FIX
    line gives a command that makes one."""
    return _checked(value, setting, least=MIN_SECRET_BYTES)


def shared_secret(value: str) -> SecretStr:
    """`value` as a shared secret, in a group's validator: what `secret` checks, failing with a
    ValueError of fixed text, which pydantic collects with the load's other failures, so the
    settings name them all; a ConfigurationError raised there would stop the load at the
    first."""
    problem = _problem(value, least=MIN_SECRET_BYTES)
    if problem is not None:
        why, fix = problem
        raise ValueError(f"{why}; {fix.rstrip('.')}")
    return SecretStr(value)


def _checked(value: str, setting: str, *, least: int) -> SecretStr:
    """`value` as a key of at least `least` bytes, or ConfigurationError naming `setting`."""
    problem = _problem(value, least=least)
    if problem is not None:
        why, fix = problem
        raise ConfigurationError(f"{setting} {why}. FIX: {fix}", details={"setting": setting})
    return SecretStr(value)


def _problem(value: str, *, least: int) -> tuple[str, str] | None:
    """What is wrong with `value` as a key of at least `least` bytes, and its fix, in fixed text;
    None when nothing is."""
    if not _KEY.fullmatch(value):
        why = (
            "holds a character no API key holds: a space or a line break inside it, or a "
            "control or non-ASCII character"
        )
        return why, "give the key alone, on one line."
    if len(value.encode("utf-8")) < least:
        return f"holds a secret shorter than {least} bytes", f"make a new one with {GENERATOR}"
    return None


def read_secret_file(path: Path, setting: str) -> str | None:
    """The contents of the secret file `path` (a byte-order mark dropped, as Notepad and Windows
    PowerShell 5.1 may write one), with the space around them removed; None when it holds
    nothing. A file that cannot be opened or read, or whose text is not UTF-8 (a NUL in it, as
    UTF-16 written with no byte-order mark holds), raises ConfigurationError naming `setting`,
    never the file's path or its bytes, with the FIX for which it is."""
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError:  # it holds the file's bytes: not chained
        why, fix = "is not UTF-8 text", NOT_UTF8
    except OSError as error:
        why, fix = f"cannot be read ({type(error).__name__})", UNREADABLE
    else:
        if "\x00" not in text:
            return text or None
        why, fix = "is not UTF-8 text", NOT_UTF8
    raise ConfigurationError(
        f"{setting} is set, but the file {why}. {fix}", details={"setting": setting}
    )
