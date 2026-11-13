"""Who is calling and what they consented to (the design's 5.2 and 6.5): parsed strictly, since a
token's claims are outside input, bounded, read-only, and refused without echoing a value
(GP-19), a signed consent as strictly as a plain one."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.identity import (
    CONSENT_SEAL,
    CONSENT_VERSION_PATTERN,
    MAX_ATTRIBUTES,
    MAX_TEXT,
    Caller,
    Consent,
    SignedConsent,
)
from t2_agentic_voice.core.settings.privacy import PrivacySettings

from tests.leaks import holding, shown

MARK = "zx-made-up-mark-41"  # a value no error may repeat
LONG = MARK * 15  # over MAX_TEXT
# Where a model's own refusal carries the input it refused, as pydantic's always do: an identity
# source's `verify` answers with a JoinRejected that holds no value, never with these.
CARRIED = {"errors", "errors json"}


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
