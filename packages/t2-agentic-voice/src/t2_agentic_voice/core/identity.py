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
be recorded (invariant 8), so a consent built anywhere else, `DevIdentity`'s or a team's own
verifier's, never turns recording on, whatever it says. Two guards keep it to the verifier. At
run time, a `SignedConsent` is built only by a validation given `CONSENT_SEAL` as its context,
which records that very instance as sealed, and the usual ways to build or change one raise
TypeError; `allows_recording(consent)`, which every other layer asks, is true only for the
instance the seal validated, alive and unchanged since, so a copy, a rebuilt or re-typed
consent, or one whose fields were rewritten allows nothing. Statically, `[[restricted]]`
(ARCH-CONSTRUCT) reports a call that builds a `SignedConsent` outside `adapters`, and any
mention of the seal's name outside adapters/join_tokens.py and this module, in the library or
an app; a `TypeAdapter` of the class, or a model with a field of it, the seal alone guards.
What gets past both is deliberate, for review: the seal named or found at run time, memory
rewritten through `ctypes`, a write to this module's registry (invariant 8 lists them).
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Annotated, Any, Final, Self, final

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
# The seal a validation of a `SignedConsent` is given as its context; only adapters/join_tokens.py
# and this module name it (`[[restricted]]`, every mention counted). Compared by identity: a copy
# is no seal.
CONSENT_SEAL: Final[object] = object()
_UNSEALED = (
    "Only adapters' SignedJoinTokens builds a SignedConsent, from a token whose signature it "
    "verified; elsewhere, pass on the Consent the identity source returned, or build a plain "
    "Consent, which never turns recording on."
)


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


@dataclass(frozen=True, slots=True)
class _Sealed:
    """A `SignedConsent` as the seal validated it: a weak reference to that very instance, the
    `__dict__` that holds its fields (a re-called `__init__` gives it another), and each field's
    value then."""

    consent: weakref.ref[SignedConsent]
    fields: dict[str, Any]
    values: tuple[tuple[str, Any], ...]

    def holds(self, consent: Consent) -> bool:
        """Whether `consent` is that instance, alive, each field still the same object."""
        fields = consent.__dict__
        return (
            self.consent() is consent
            and fields is self.fields
            and len(fields) == len(self.values)
            and all(name in fields and fields[name] is value for name, value in self.values)
        )


# Each `SignedConsent` the seal validated, by its id(): only this module reads or writes it. An
# entry goes when its consent is collected (the weak reference's callback runs before the id is
# free again), so the registry never outgrows the consents alive.
_SEALED: dict[int, _Sealed] = {}


def _forget(key: int, _: object) -> None:
    """Drops the entry of a collected consent."""
    _SEALED.pop(key, None)


@final
class SignedConsent(Consent):
    """The consent a verified signed join token carried: built only by the identity source that
    verified the token's signature (`SignedJoinTokens`, in `adapters`; `[[restricted]]`), as
    `SignedConsent.model_validate(data, context=CONSENT_SEAL)`, a validation that records the
    instance as sealed. It never equals a plain `Consent` that holds the same choices. The call's
    recorder keeps audio only when `privacy.record_audio` is on and `allows_recording(consent)`
    (invariant 8), true only for the very instance the seal validated, unchanged since: any other
    `SignedConsent` allows nothing, however it came about.

    So that the common mistakes fail loudly, these raise TypeError: its constructor,
    `type(c)(...)` included, since pydantic's `__init__` passes no context (re-called on an
    instance, it rewrites that instance before it raises, which then allows nothing); a
    validation without the seal (`model_validate`, `model_validate_json`, a `TypeAdapter`, a
    model that holds one); `model_construct`, which skips validation; `model_copy` with an update
    (`__replace__` calls it), and pydantic's deprecated `copy` given `update`, `include` or
    `exclude`, neither of which validates, so even the seal's holder builds a changed consent
    anew; and a subclass, as it is defined or, past a mixin that skips `__init_subclass__`, as
    it is validated. What these refusals do not see allows nothing: a copy of any kind, even with
    no change (pydantic's base `model_copy`, `copy.copy`, `copy.deepcopy`, a pickle), a plain
    consent whose `__class__` is set to this class, and a field written in place."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(f"SignedConsent takes no subclass. {_UNSEALED}")

    def model_post_init(self, context: Any, /) -> None:
        """Refuses the consent unless its validation was given the seal as its context, and
        records the instance as sealed: pydantic calls this after every validation, with its
        context, and after `model_construct`, with none. A subclass's instance is refused."""
        if context is not CONSENT_SEAL or type(self) is not SignedConsent:
            raise TypeError(_UNSEALED)
        key, fields = id(self), self.__dict__
        sealed = weakref.ref(self, partial(_forget, key))
        _SEALED[key] = _Sealed(sealed, fields, tuple(fields.items()))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A copy of this consent, which allows nothing; never one with an `update`, which
        pydantic does not validate."""
        if update:
            raise TypeError(_UNSEALED)
        return super().model_copy(deep=deep)

    def copy(
        self,
        *,
        include: object = None,
        exclude: object = None,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Pydantic's deprecated copy, which allows nothing; never given `update`, `include` or
        `exclude`, which it neither validates nor checks."""
        if include is not None or exclude is not None or update is not None:
            raise TypeError(_UNSEALED)
        return super().copy(deep=deep)


def allows_recording(consent: Consent) -> bool:
    """Whether `consent` lets the call's audio be kept (invariant 8): only the very
    `SignedConsent` the seal validated, the consent of a token whose signature was verified,
    alive and unchanged since, that says `record_audio`. A copy of it, or a consent rebuilt,
    re-typed or rewritten in place, allows nothing. Every layer but `adapters` asks this rather
    than naming the class."""
    sealed = _SEALED.get(id(consent))
    return (
        type(consent) is SignedConsent
        and sealed is not None
        and sealed.holds(consent)
        and consent.record_audio is True
    )
