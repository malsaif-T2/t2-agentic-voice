"""Who is calling and what they consented to (the design's 5.2 and 6.5): parsed strictly, since a
token's claims are outside input, bounded, read-only, and refused without echoing a value
(GP-19); and only the consent a verified signed token carried, which only `adapters` builds,
can let audio be recorded (docs/SECURITY.md, invariant 8): every other way to build one raises
at run time, and `poe arch` reports the seal's name anywhere but in `adapters`."""

from __future__ import annotations

import ast
import copy
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError, create_model
from t2_agentic_voice.core import identity
from t2_agentic_voice.core.identity import (
    CONSENT_SEAL,
    CONSENT_VERSION_PATTERN,
    MAX_ATTRIBUTES,
    MAX_TEXT,
    Caller,
    Consent,
    SignedConsent,
    allows_recording,
)
from t2_agentic_voice.core.identity import SignedConsent as Verified
from t2_agentic_voice.core.settings.privacy import PrivacySettings

from scripts.arch_module import ModuleChecker
from scripts.harness_config import load_config
from tests.leaks import holding, shown

ROOT = Path(__file__).resolve().parents[3]
MARK = "zx-made-up-mark-41"  # a value no error may repeat
LONG = MARK * 15  # over MAX_TEXT
# Where a model's own refusal carries the input it refused, as pydantic's always do: Track C's
# `verify` answers with a JoinRejected that holds no value, never with these.
CARRIED = {"errors", "errors json"}
RECORD: dict[str, Any] = {"version": "v1", "record_audio": True}
RECORD_JSON = '{"version": "v1", "record_audio": true}'


def _signed(*, record_audio: bool) -> SignedConsent:
    """A consent as `SignedJoinTokens` builds one, from a token whose signature it verified."""
    data = {"version": "v1", "record_audio": record_audio}
    return SignedConsent.model_validate(data, context=CONSENT_SEAL)


def _refused(model: type[Caller | Consent], data: dict[str, Any]) -> ValidationError:
    with pytest.raises(ValidationError) as raised:
        model.model_validate(data)
    return raised.value


def test_a_caller_holds_the_tokens_identity_read_only() -> None:
    caller = Caller(
        subject="e-1042", display_name="Sara", locale="ar-SA", attributes={"dept": "it"}
    )
    assert (caller.subject, caller.display_name, caller.locale) == ("e-1042", "Sara", "ar-SA")
    assert Caller(subject="dev") == Caller(subject="dev", attributes={})
    with pytest.raises(TypeError):
        caller.attributes["dept"] = "finance"  # type: ignore[index]
    with pytest.raises(ValidationError):
        caller.subject = "e-1"  # type: ignore[misc]
    assert caller.model_dump(mode="json")["attributes"] == {"dept": "it"}
    assert Caller.model_validate_json(caller.model_dump_json()) == caller


@pytest.mark.parametrize(
    "bad",
    [
        {"subject": ""},
        {"subject": "   "},
        {"subject": f"e-1\n{MARK}"},
        {"subject": f"e-1\x1b{MARK}"},
        {"subject": LONG},
        {"subject": 1042},
        {"subject": "e-1", "display_name": f"{MARK}\r\n"},
        {"subject": "e-1", "locale": f"{MARK} please"},
        {"subject": "e-1", "locale": "ab" + "-abcdefgh" * 4},  # over 35 characters
        {"subject": "e-1", "attributes": {f"{MARK} key": "v"}},
        {"subject": "e-1", "attributes": {MARK: LONG}},
        {"subject": "e-1", "attributes": {MARK: f"{MARK}\n"}},
        {"subject": "e-1", "attributes": {MARK: 1}},
        {"subject": "e-1", "attributes": {f"k{i}": MARK for i in range(MAX_ATTRIBUTES + 1)}},
        {"subject": "e-1", "attributes": [MARK]},
        {"subject": "e-1", "role": MARK},
    ],
)
def test_a_caller_refuses_what_a_token_should_not_carry_and_echoes_none_of_it(
    bad: dict[str, Any],
) -> None:
    """A key of `attributes` is outside input too: no error's text names it. Its `errors()`
    and `json()` carry the input, as pydantic's always do."""
    assert len(LONG) > MAX_TEXT
    error = _refused(Caller, bad)
    assert set(holding(MARK, shown(error))) <= CARRIED


def test_a_caller_takes_names_in_any_script_up_to_the_bound() -> None:
    caller = Caller(subject="x" * MAX_TEXT, display_name="سارة العتيبي", locale="en")
    assert caller.display_name == "سارة العتيبي"
    keys = {f"k{i}": "v" for i in range(MAX_ATTRIBUTES)}
    assert len(Caller(subject="e-1", attributes=keys).attributes) == MAX_ATTRIBUTES


@pytest.mark.parametrize(
    "bad",
    [
        {"version": None, "record_audio": "true"},
        {"version": None, "record_audio": "false"},
        {"version": None, "record_audio": 1},
        {"version": None, "record_audio": 0},
        {"version": None, "record_audio": None},
        {"version": None},
        {"record_audio": False},
        {"version": f"{MARK} 2", "record_audio": False},
        {"version": MARK * 4, "record_audio": False},  # over 64 characters
        {"version": "", "record_audio": False},
        {"version": 2, "record_audio": False},
        {"version": "v1", "record_audio": False, "scope": MARK},
    ],
)
def test_a_consent_is_a_bounded_version_and_a_real_boolean(bad: dict[str, Any]) -> None:
    """The plan's adversarial cases for `consent.record_audio` ("true", "false", 1, null) and
    the bounded version, refused whether parsed from a token's claims or built in code, and by
    a signed consent too: the seal skips none of the parsing."""
    error = _refused(Consent, bad)
    assert set(holding(MARK, shown(error))) <= CARRIED
    with pytest.raises(ValidationError) as raised:
        SignedConsent.model_validate(bad, context=CONSENT_SEAL)
    assert set(holding(MARK, shown(raised.value))) <= CARRIED


def test_a_consent_version_is_what_the_setting_takes() -> None:
    """/join compares the two, so one pattern bounds both."""
    pattern = next(
        m.pattern
        for m in PrivacySettings.model_fields["consent_version"].metadata
        if hasattr(m, "pattern")
    )
    assert pattern == CONSENT_VERSION_PATTERN
    assert Consent(version="m2-owner-test-1", record_audio=True).version == "m2-owner-test-1"
    assert PrivacySettings(consent_version="m2-owner-test-1").consent_version == "m2-owner-test-1"


class _Holder(BaseModel):
    consent: SignedConsent


_BOUND = identity.SignedConsent  # a name bound to the class


def _replaced(consent: SignedConsent) -> object:
    """What Python 3.13's `copy.replace(consent, record_audio=True)` calls: pydantic's
    `__replace__`, which typeshed's 3.12 does not name."""
    replace = consent.__replace__  # type: ignore[attr-defined]
    return replace(record_audio=True)


# The ways the review found to build a signed consent outside adapters, and their kin, each
# refused at run time: `consent` is one the verifier built.
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
    "a model that holds one": lambda _: _Holder.model_validate({"consent": RECORD}),
    "model_construct": lambda _: SignedConsent.model_construct(**RECORD),
    "model_copy with an update": lambda consent: consent.model_copy(update={"record_audio": True}),
    "a deep model_copy with an update": lambda consent: consent.model_copy(
        update={"record_audio": True}, deep=True
    ),
    "__replace__": _replaced,
}


@pytest.mark.parametrize("build", UNSEALED.values(), ids=UNSEALED.keys())
def test_a_signed_consent_is_built_no_other_way(build: Callable[[SignedConsent], object]) -> None:
    """Whatever the code that tries, even with a declined verified consent in hand: no new
    `SignedConsent` comes out, and the refusal says who builds one."""
    with pytest.raises(TypeError, match="Only adapters' SignedJoinTokens builds a SignedConsent"):
        build(_signed(record_audio=False))


def test_a_signed_consent_takes_no_subclass() -> None:
    with pytest.raises(TypeError, match="takes no subclass"):

        class Mine(SignedConsent):  # type: ignore[misc]
            pass

    with pytest.raises(TypeError, match="takes no subclass"):
        create_model("Mine", __base__=SignedConsent)


@pytest.mark.parametrize(
    "same",
    [
        lambda c: c.model_copy(),
        lambda c: c.model_copy(update={}),
        lambda c: c.model_copy(deep=True),
        copy.copy,
        copy.deepcopy,
        lambda c: pickle.loads(pickle.dumps(c)),  # noqa: S301 (the test's own consent)
    ],
    ids=["model_copy", "an empty update", "deep", "copy", "deepcopy", "pickle"],
)
def test_a_copy_with_no_change_is_the_same_consent(
    same: Callable[[SignedConsent], SignedConsent],
) -> None:
    for signed in (_signed(record_audio=True), _signed(record_audio=False)):
        copied = same(signed)
        assert type(copied) is SignedConsent and copied == signed
        assert allows_recording(copied) is allows_recording(signed)


def test_only_a_signed_consent_is_a_verified_tokens_and_only_adapters_build_one() -> None:
    signed = _signed(record_audio=True)
    plain = Consent(version="v1", record_audio=True)
    assert isinstance(signed, Consent) and not isinstance(plain, SignedConsent)
    assert signed != plain  # the same choices, but not from a verified token
    assert type(Consent.model_validate(signed.model_dump())) is Consent
    assert allows_recording(signed) is True
    assert allows_recording(_signed(record_audio=False)) is False
    assert allows_recording(plain) is False  # DevIdentity's, or a team's own verifier's
    assert _Holder.model_validate({"consent": RECORD}, context=CONSENT_SEAL).consent == signed


# What a module outside adapters might write to reach the seal or build a signed consent, read
# by `poe arch` with this repository's harness.toml as Track D's recorder and Track C's verifier.
REACHES = {
    "the seal imported under another name": (
        "from t2_agentic_voice.core.identity import CONSENT_SEAL as S\n"
    ),
    "the seal imported relatively": "from ...core.identity import CONSENT_SEAL\n",
    "a name bound to the seal": (
        "from t2_agentic_voice.core import identity\nseal = identity.CONSENT_SEAL\n"
    ),
    "the seal by getattr": (
        "from t2_agentic_voice.core import identity\nseal = getattr(identity, 'CONSENT_SEAL')\n"
    ),
    "the seal's name read": "from t2_agentic_voice.core.identity import *\nseal = CONSENT_SEAL\n",
    "the class called": "SignedConsent(version=None, record_audio=True)\n",
    "the class validated": "identity.SignedConsent.model_validate({})\n",
}


def _construct_lines(source: str, *, rel: str) -> list[int]:
    """The lines ARCH-CONSTRUCT reports in `source`, as the library's module `rel`."""
    checker = ModuleChecker(load_config(ROOT).arch, layer=rel.split("/")[0], rel=rel, display=rel)
    checker.visit(ast.parse(source))
    return [v.line for v in checker.violations if v.rule == "ARCH-CONSTRUCT"]


@pytest.mark.parametrize("source", REACHES.values(), ids=REACHES.keys())
def test_poe_arch_reports_the_seal_and_the_class_outside_adapters(source: str) -> None:
    assert _construct_lines(source, rel="voice/session/recording.py") == [len(source.splitlines())]
    assert _construct_lines(source, rel="adapters/join_tokens.py") == []


def test_only_the_module_that_makes_the_seal_reads_it_unreported() -> None:
    """core/identity.py checks the seal by its name; any other module of `core` is reported."""
    source = (ROOT / "packages/t2-agentic-voice/src/t2_agentic_voice/core/identity.py").read_text(
        encoding="utf-8"
    )
    assert "CONSENT_SEAL" in source
    assert _construct_lines(source, rel="core/identity.py") == []
    assert _construct_lines("seal = CONSENT_SEAL\n", rel="core/events.py") == [1]
