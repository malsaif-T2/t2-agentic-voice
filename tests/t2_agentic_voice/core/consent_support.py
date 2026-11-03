"""What the consent tests share (test_identity.py): a consent as the verifier builds one, and
the ways the reviews found to build or change a signed consent outside adapters, with their
kin: those refused at run time, and those that give a consent that allows nothing."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter
from t2_agentic_voice.core import identity
from t2_agentic_voice.core.identity import CONSENT_SEAL, Consent, SignedConsent
from t2_agentic_voice.core.identity import SignedConsent as Verified

RECORD: dict[str, Any] = {"version": "v1", "record_audio": True}
RECORD_JSON = '{"version": "v1", "record_audio": true}'
UPDATE: dict[str, Any] = {"record_audio": True}


def verified(*, record_audio: bool) -> SignedConsent:
    """A consent as `SignedJoinTokens` builds one, from a token whose signature it verified."""
    data = {"version": "v1", "record_audio": record_audio}
    return SignedConsent.model_validate(data, context=CONSENT_SEAL)


class Holder(BaseModel):
    consent: SignedConsent


_BOUND = identity.SignedConsent  # a name bound to the class


class _Quiet:
    """A mixin whose `__init_subclass__` does not chain, so a subclass skips SignedConsent's."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        pass


class MixedIn(_Quiet, SignedConsent):  # type: ignore[misc]
    """A subclass past the refusal at its definition: refused as it is validated."""


class Unchecked(_Quiet, SignedConsent):  # type: ignore[misc]
    """One that skips the seal's check as well: it builds, and allows nothing."""

    def model_post_init(self, context: Any, /) -> None:
        pass


def _replaced(consent: SignedConsent) -> object:
    """What Python 3.13's `copy.replace(consent, record_audio=True)` calls: pydantic's
    `__replace__`, which typeshed's 3.12 does not name."""
    replace = consent.__replace__  # type: ignore[attr-defined]
    return replace(record_audio=True)


# The ways the reviews found to build or change a signed consent outside adapters, and their kin,
# each refused at run time: `consent` is one the verifier built.
UNSEALED: dict[str, Callable[[SignedConsent], object]] = {
    "the constructor": lambda _: SignedConsent(version="v1", record_audio=True),
    "an import alias": lambda _: Verified(version="v1", record_audio=True),
    "a name bound to the class": lambda _: _BOUND(**RECORD),
    "type(consent)(...)": lambda consent: type(consent)(**RECORD),
    "consent.__class__(...)": lambda consent: consent.__class__(**RECORD),
    "type(consent).model_validate": lambda consent: type(consent).model_validate(RECORD),
    "model_validate": lambda _: SignedConsent.model_validate(RECORD),
    "model_validate_json": lambda _: SignedConsent.model_validate_json(RECORD_JSON),
    "model_validate_strings": lambda _: SignedConsent.model_validate_strings(
        {"version": "v1", "record_audio": "true"}
    ),
    "from a plain consent's attributes": lambda _: SignedConsent.model_validate(
        Consent(**RECORD), from_attributes=True
    ),
    "a seal of its own": lambda _: SignedConsent.model_validate(RECORD, context=object()),
    "a copy of the seal": lambda _: SignedConsent.model_validate(
        RECORD, context=copy.copy(CONSENT_SEAL)
    ),
    "the seal inside a context": lambda _: SignedConsent.model_validate(
        RECORD, context={"seal": CONSENT_SEAL}
    ),
    "TypeAdapter.validate_python": lambda _: TypeAdapter(SignedConsent).validate_python(RECORD),
    "TypeAdapter.validate_json": lambda _: TypeAdapter(SignedConsent).validate_json(RECORD_JSON),
    "a model that holds one": lambda _: Holder.model_validate({"consent": RECORD}),
    "model_construct": lambda _: SignedConsent.model_construct(**RECORD),
    "model_copy with an update": lambda consent: consent.model_copy(update={"record_audio": True}),
    "a deep model_copy with an update": lambda consent: consent.model_copy(
        update={"record_audio": True}, deep=True
    ),
    "__replace__": _replaced,
    "the deprecated copy with an update": lambda consent: consent.copy(update=UPDATE),
    "a deep deprecated copy with an update": lambda c: c.copy(update=UPDATE, deep=True),
    "the deprecated copy with include": lambda consent: consent.copy(include={"version"}),
    "the deprecated copy with exclude": lambda consent: consent.copy(exclude={"version"}),
    "a subclass past its refusal, sealed": lambda _: MixedIn.model_validate(
        RECORD, context=CONSENT_SEAL
    ),
}


def deprecated[T](copied: Callable[[], T]) -> T:
    """`copied()`, a call of pydantic's deprecated `copy`, which warns that it is."""
    with pytest.deprecated_call():
        return copied()


def _rebuilt(consent: SignedConsent) -> object:
    """`__init__` called again on the instance: pydantic rewrites it, then the seal's check
    raises, too late to keep the instance as it was."""
    with pytest.raises(TypeError, match="Only adapters' SignedJoinTokens"):
        consent.__init__(version="v1", record_audio=True)
    return consent


def _revalidated(consent: SignedConsent) -> object:
    """Its own values validated into the instance again by `Consent`'s validator, which checks
    no seal, so nothing raises."""
    data = {"version": consent.version, "record_audio": consent.record_audio}
    Consent.__pydantic_validator__.validate_python(data, self_instance=consent)
    return consent


def _written(consent: SignedConsent) -> object:
    """Its fields written through `object.__setattr__`, past the frozen check."""
    object.__setattr__(consent, "version", "v2")
    object.__setattr__(consent, "record_audio", True)
    return consent


def _written_in_dict(consent: SignedConsent) -> object:
    """Its fields written in its `__dict__`."""
    consent.__dict__.update(version="v2", record_audio=True)
    return consent


def _assigned(consent: SignedConsent) -> object:
    """A validated assignment, which pydantic's frozen check does not see."""
    validator = SignedConsent.__pydantic_validator__
    validator.validate_assignment(consent, "version", "v2")
    validator.validate_assignment(consent, "record_audio", True)
    return consent


def _retyped(consent: SignedConsent) -> object:
    """A plain consent that says `record_audio`, its `__class__` set to the verified one's."""
    plain = Consent(version="v1", record_audio=True)
    plain.__class__ = type(consent)
    return plain


def _retyped_by_object(consent: SignedConsent) -> object:
    """The same, through `object.__setattr__`."""
    plain = Consent(version="v1", record_audio=True)
    object.__setattr__(plain, "__class__", type(consent))
    return plain


def _restored(consent: SignedConsent) -> object:
    """A new instance given another state with pydantic's `__setstate__`, as a crafted pickle
    does."""
    made = type(consent).__new__(type(consent))
    made.__setstate__({**consent.__getstate__(), "__dict__": dict(RECORD)})
    return made


# What gets past the refusals: each gives a consent that allows nothing, though it may be a
# `SignedConsent` that reads as the verified one did or says `record_audio`. `consent` is one
# the verifier built, which some of them change in place.
ALLOWS_NOTHING: dict[str, Callable[[SignedConsent], object]] = {
    "Consent.model_copy with an update": lambda c: Consent.model_copy(c, update=UPDATE),
    "a deep Consent.model_copy": lambda c: Consent.model_copy(c, update=UPDATE, deep=True),
    "BaseModel.model_copy with an update": lambda c: BaseModel.model_copy(c, update=UPDATE),
    "super().model_copy with an update": lambda c: super(SignedConsent, c).model_copy(
        update=UPDATE
    ),
    "Consent.model_copy with a value no bool": lambda c: Consent.model_copy(
        c, update={"record_audio": "yes"}
    ),
    "Consent.copy with an update": lambda c: deprecated(lambda: Consent.copy(c, update=UPDATE)),
    "a deepcopy whose memo turns False into True": lambda c: copy.deepcopy(c, {id(False): True}),
    "__setstate__ on a new instance": _restored,
    "__init__ called again": _rebuilt,
    "validated again into the instance": _revalidated,
    "fields written with object.__setattr__": _written,
    "fields written in __dict__": _written_in_dict,
    "a validated assignment": _assigned,
    "a plain consent's __class__ assigned": _retyped,
    "a plain consent's __class__ set with object.__setattr__": _retyped_by_object,
    "a subclass that skips the seal's check": lambda _: Unchecked.model_validate(
        RECORD, context=CONSENT_SEAL
    ),
}
