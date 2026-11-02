"""Who is calling, and what they consented to (the design's 5.2 and 6.5): types every layer
shares (ARCHITECTURE.md, "Conventions").

An identity source (domain's `IdentityVerifier` port) gives a call its `Caller` and `Consent`
once, at join, from the caller's join token, and nothing said or sent in the call changes either
(docs/SECURITY.md, invariant 3; no client message carries them, the design's 5.5). A join token
is signed, not encrypted, so the caller can read every value here: none holds a secret.

Both are parsed strictly at the boundary, a token's claims being outside input: each text a
bounded string with no control character, `record_audio` a real boolean (never "true" or 1).
The bounds are the agent's choice, wide enough for a directory's names and IDs, so a token
stays well under a request's size.

Only a `SignedConsent`, the consent a verified signed join token carried, can let a call's audio
be recorded (invariant 8): only `adapters` builds one (`[[restricted]]`, ARCH-CONSTRUCT), so a
consent built anywhere else, `DevIdentity`'s or a team's own verifier's, never turns recording
on, whatever it says.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_serializer,
    field_validator,
)

# A consent version: 1 to 64 printable ASCII characters with no space, as the setting
# `privacy.consent_version` takes it (core/settings/privacy.py), since /join compares the two.
CONSENT_VERSION_PATTERN = r"^[\x21-\x7e]{1,64}$"
# A locale, as a BCP 47 tag is written ("ar-SA", "en"), at most 35 characters (RFC 5646, 4.4.1).
LOCALE_PATTERN = r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$"
# An attribute's name: a short identifier.
ATTRIBUTE_NAME_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
MAX_TEXT = 256  # the longest subject, display name or attribute value, in characters
MAX_ATTRIBUTES = 16  # the most attributes a caller carries


def _printable(value: str) -> str:
    """`value`, when it holds a character and none that is not printable (a line break, a
    control or a format character); the error never repeats the value."""
    if not value.strip():
        raise ValueError("must hold a character other than a space")
    if not value.isprintable():
        raise ValueError("must hold printable characters only: no line break or control")
    return value


_Text = Annotated[str, Field(max_length=MAX_TEXT), AfterValidator(_printable)]
_Locale = Annotated[str, Field(max_length=35, pattern=LOCALE_PATTERN)]
ConsentVersion = Annotated[str, Field(pattern=CONSENT_VERSION_PATTERN)]
_ATTRIBUTE_NAME = re.compile(ATTRIBUTE_NAME_PATTERN)


def _attributes(value: object) -> object:
    """`value` when it is a map of at most MAX_ATTRIBUTES names to texts, every name an
    identifier and every text bounded and printable. Checked whole, before pydantic reads each
    entry, whose error would name the entry's key: a key is outside input too, never repeated."""
    if not isinstance(value, Mapping):
        raise ValueError("must be an object of names to texts")
    if len(value) > MAX_ATTRIBUTES:
        raise ValueError(f"must hold at most {MAX_ATTRIBUTES} attributes")
    for name, text in value.items():
        if not (isinstance(name, str) and _ATTRIBUTE_NAME.fullmatch(name)):
            raise ValueError("each name must be 1 to 64 letters, digits, dots, dashes or _")
        if not (isinstance(text, str) and len(text) <= MAX_TEXT):
            raise ValueError(f"each value must be a text of at most {MAX_TEXT} characters")
        _printable(text)
    return value


class Caller(BaseModel):
    """The verified identity of the person on a call. `subject` is the identity source's stable
    ID for them; `display_name` how they are named; `locale` the language their account prefers,
    a BCP 47 tag; `attributes` a small map of the team's own strings (a department, a role),
    read-only. It travels in a token the caller can read, so it never holds a secret."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    subject: _Text
    display_name: _Text | None = None
    locale: _Locale | None = None
    attributes: Annotated[Mapping[str, str], BeforeValidator(_attributes)] = Field(
        default_factory=dict
    )

    @field_validator("attributes", mode="after")
    @classmethod
    def _read_only(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        """The attributes as a map nothing can change, so a caller stays as the token made it."""
        return MappingProxyType(dict(value))

    @field_serializer("attributes")
    def _plain(self, value: Mapping[str, str]) -> dict[str, str]:
        """Dumped as a plain object, as it was given."""
        return dict(value)


class Consent(BaseModel):
    """What the caller chose on the consent screen: the `version` of the text they agreed to
    (None when the team versions none), and whether they agreed to have the call's audio
    recorded. A team builds one to mint a join token; a call's own comes only from its identity
    source, and only a `SignedConsent` lets audio be recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    version: ConsentVersion | None
    record_audio: StrictBool


class SignedConsent(Consent):
    """The consent a verified signed join token carried: built only by the identity source that
    verified the token's signature (`SignedJoinTokens`, in `adapters`; `[[restricted]]`). It
    never equals a plain `Consent` that holds the same choices. The call's recorder keeps audio
    only when `privacy.record_audio` is on and the call's consent is one of these with
    `record_audio` true (invariant 8)."""
