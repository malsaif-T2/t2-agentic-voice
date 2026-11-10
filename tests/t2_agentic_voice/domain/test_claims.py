"""The output guard's rule A (domain/claims.py; docs/SECURITY.md, invariant 2): no clause claims
an action, or holds an action's number, unless the call's record or a `reports_on` result holds
it. Adversarial (GP-08): model text claiming a ticket was made, a passage holding a fake number,
a number never issued; each blocked without evidence and passed with it. Every number here is
made up for the test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.claims import (
    ActionEvidence,
    ClaimVerdict,
    any_action_claims,
    check_claims,
    default_claims,
    holds_an_id,
)
from t2_agentic_voice.domain.guard_ids import guard_form

SETTINGS = GuardSettings()
TICKET = "2026110482000123"  # the made-up number the backend issued
FAKE = "2026110482000999"  # one a passage carries, never issued
# A team's own phrases for its action, in each language.
CLAIMS: Mapping[str, Sequence[str]] = {"create_ticket": ("opened your ticket", "ticket opened")}
ARABIC_CLAIMS: Mapping[str, Sequence[str]] = {"create_ticket": ("فتحت لك التذكرة",)}
MADE = ActionEvidence(action="create_ticket", texts=(f'{{"ticket_number": "{TICKET}"}}',))


def _check(
    clause: str,
    *evidence: ActionEvidence,
    code: LanguageCode = "en",
    claims: Mapping[str, Sequence[str]] | None = None,
    settings: GuardSettings = SETTINGS,
) -> ClaimVerdict:
    own = claims if claims is not None else (CLAIMS if code == "en" else ARABIC_CLAIMS)
    return check_claims(
        clause,
        claims=own,
        any_action=default_claims(code),
        evidence=evidence,
        settings=settings,
        year=2026,
    )


@pytest.mark.parametrize(
    ("clause", "code"),
    [
        ("I've created a ticket for you.", "en"),
        ("I have submitted your request to the support team.", "en"),
        ("Your ticket has been created.", "en"),
        ("Great news, I’ve opened your ticket!", "en"),  # the team's own phrase, a curly mark
        ("تم إنشاء التذكرة بنجاح.", "ar"),
        ("وتمّ إنشاء تذكرتك.", "ar"),  # after waw, with a shadda
        ("سجلت لك الطلب، وراح يتواصلون معك.", "ar"),
        ("لقد أنشأت التذكرة.", "ar"),
        ("فتحت لك التذكرة.", "ar"),
    ],
)
def test_model_text_claiming_an_action_is_blocked_without_a_record(
    clause: str, code: LanguageCode
) -> None:
    verdict = _check(clause, code=code)
    assert verdict.passed is False
    assert _check(clause, MADE, code=code).passed is True


def test_a_teams_phrase_names_its_action_and_a_default_any_action_with_evidence() -> None:
    assert _check("Ticket opened.").claimed == ("create_ticket",)
    other = ActionEvidence(action="hand_off", texts=())
    assert _check("I've created it.", MADE, other).claimed == ("create_ticket", "hand_off")
    assert _check("I've created it.") == ClaimVerdict(claimed=(), passed=False)


def test_a_claim_of_one_action_is_no_claim_of_another() -> None:
    handed = ActionEvidence(action="hand_off", texts=(f"ticket {TICKET}",))
    verdict = _check("Ticket opened.", handed)
    assert verdict == ClaimVerdict(claimed=("create_ticket",), passed=False)


@pytest.mark.parametrize(
    "clause",
    [
        f"I've created your ticket, its number is {FAKE}.",
        f"تم إنشاء تذكرتك ورقمها {FAKE}",
    ],
)
def test_a_passages_fake_number_in_a_claim_is_blocked_even_with_a_record(clause: str) -> None:
    """The passage holding it is no evidence for rule A: only the action's result is."""
    code: LanguageCode = "en" if clause.startswith("I") else "ar"
    assert _check(clause, code=code) == ClaimVerdict(claimed=(), passed=False, unsupported=(FAKE,))
    verdict = _check(clause, MADE, code=code)
    assert verdict == ClaimVerdict(claimed=("create_ticket",), passed=False, unsupported=(FAKE,))
    issued = ActionEvidence(action="create_ticket", texts=(f"number {FAKE}",))
    assert _check(clause, issued, code=code).passed


def test_a_number_never_issued_is_blocked_and_the_issued_one_passes() -> None:
    never = _check("Your ticket 4521 3390 has been created.", MADE)
    assert never.passed is False and never.unsupported == ("45213390",)
    assert _check(f"Your ticket {TICKET} has been created.", MADE).passed


@pytest.mark.parametrize(
    "said",
    [
        "4521 3390",
        "45 21 33 90",
        "4521-3390",
        "٤٥٢١٣٣٩٠",
        "four five two one three three nine zero",
    ],
)
def test_a_number_spaced_or_said_digit_by_digit_is_the_number(said: str) -> None:
    clause = f"I've opened your ticket, number {said}."
    issued = ActionEvidence(action="create_ticket", texts=('{"number": "45213390"}',))
    assert _check(clause, issued).passed
    other = ActionEvidence(action="create_ticket", texts=('{"number": "45213391"}',))
    assert _check(clause, other).unsupported == ("45213390",)


def test_a_status_result_supports_the_claim_and_its_number() -> None:
    """A `reports_on` tool's result is evidence for the action it reports on."""
    status = ActionEvidence(action="create_ticket", texts=(f'{{"{TICKET}": "open"}}',))
    assert _check(f"Your ticket {TICKET} has been registered and is open.", status).passed


def test_a_clause_with_no_claim_phrase_passes_whatever_it_holds() -> None:
    """Its numbers are rule B's (domain/guard_ids.py)."""
    verdict = _check(f"The reference in the article is {FAKE}.")
    assert verdict == ClaimVerdict(claimed=(), passed=True)
    assert _check("To open a ticket, call the support line.").passed
    assert _check("إذا تبي ترسل مراسلة، اضغط إرسال.", code="ar").passed


def test_a_declared_pattern_in_a_claim_needs_the_actions_evidence() -> None:
    settings = GuardSettings(id_patterns=(r"LT-\d{5}",))
    issued = ActionEvidence(action="create_ticket", texts=("LT-00423",))
    clause = "I've registered LT-00423 for you."
    assert _check(clause, issued, settings=settings).passed
    assert "00423" in _check(clause, MADE, settings=settings).unsupported


@pytest.mark.parametrize(
    ("result", "held"),
    [
        ('{"tickets": [{"ends_in": "4417", "opened_on": "2025-11-02"}], "total": 1}', True),
        ('{"tickets": [], "total": 0, "asked_ends_in": null, "note": "None ends in it."}', False),
        ('{"state": "none", "opened_on": "2026-11-10", "count": 12}', False),
    ],
    ids=["a_ticket", "found_nothing", "a_date_and_a_count"],
)
def test_a_status_result_backs_a_claim_only_when_it_holds_an_id(result: str, held: bool) -> None:
    """A status that found nothing holds no record of the action (invariant 2); this year and
    the parts of a date are no ID, as in rule B."""
    assert holds_an_id([result], settings=SETTINGS, year=2026) is held


def test_the_phrases_that_claim_any_action_are_every_languages() -> None:
    found = any_action_claims({"en": ("all sorted",)})
    assert set(found) == {*default_claims("ar"), *default_claims("en"), "all sorted"}
    assert len(set(found)) == len(found)


def test_the_defaults_are_written_in_the_guards_form_each_once() -> None:
    codes: tuple[LanguageCode, ...] = ("ar", "en")
    for code in codes:
        phrases = default_claims(code)
        assert phrases and all(phrase == guard_form(phrase) for phrase in phrases)
        assert len(set(phrases)) == len(phrases)
