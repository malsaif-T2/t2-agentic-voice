"""The output guard (domain/guard.py, the design's 8.2). Its ID rule (rule B, domain/guard_ids.py):
every ID-shaped token of a clause needs evidence seen this call, after digits are normalized
(Arabic-Indic and Persian digits, digit words, digits in groups); the current year and the next
pass with none; declared patterns are ID-shaped too. Then both rules together, the claim rule
(rule A, domain/claims.py) first, the reason in the verdict. Every number here is made up for
the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.claims import ActionEvidence, default_claims
from t2_agentic_voice.domain.guard import GuardVerdict, IdVerdict, check_clause, check_ids

SETTINGS = GuardSettings()


def _check(clause: str, *evidence: str, settings: GuardSettings = SETTINGS) -> IdVerdict:
    return check_ids(clause, evidence=evidence, settings=settings, year=2026)


def test_a_clause_with_no_id_passes() -> None:
    assert _check("Open Settings, then press Reset.") == IdVerdict(passed=True)
    assert _check("You have 2 devices and 45 minutes left.").passed  # under three digits


def test_an_id_with_no_evidence_is_blocked_and_named() -> None:
    verdict = _check("Your request number is 4521.")
    assert verdict == IdVerdict(passed=False, unsupported=("4521",))


def test_an_id_in_a_tool_result_or_the_callers_words_passes() -> None:
    assert _check("Your request number is 4521.", '{"request": "4521", "status": "open"}').passed
    assert _check("Ticket 7788 is closed.", "my ticket is seven seven eight eight").passed


@pytest.mark.parametrize(
    "clause",
    [
        "Your number is ٤٥٢١.",  # Arabic-Indic digits
        "Your number is ۴۵۲۱.",  # Persian (Eastern Arabic-Indic) digits
        "Your number is four five two one.",
        "رقمك أربعة خمسة اثنين واحد",
        "Your number is 4 5 2 1.",
        "Your number is 45 21.",  # digits in groups
        "Your number is 45-21.",
    ],
)
def test_every_way_of_writing_the_digits_is_read_as_the_same_number(clause: str) -> None:
    assert _check(clause) == IdVerdict(passed=False, unsupported=("4521",))
    assert _check(clause, "Request 4521 is open.").passed


def test_an_id_read_in_groups_passes_from_its_whole_and_its_whole_from_its_groups() -> None:
    assert _check("It is 4521 3390.", "request 45213390").passed
    assert _check("It is 45213390.", "request 4521 3390").passed
    assert _check("The last two are 3390 7788.", "codes 4521 3390 7788").passed


def test_an_id_read_in_pairs_is_checked_whole() -> None:
    verdict = _check("It is 45 21 33.", "45 apples, 21 pears and 33 plums")
    assert verdict == IdVerdict(passed=False, unsupported=("452133",))


def test_a_number_inside_a_longer_one_is_no_evidence_for_it() -> None:
    assert not _check("It ends in 3390.", "request 45213390").passed


def test_the_current_year_and_the_next_pass_and_end_a_group() -> None:
    assert _check("Since 2026, and until 2027.").passed
    assert _check("On November 6 2026.").passed
    verdict = _check("In 2025.")
    assert verdict == IdVerdict(passed=False, unsupported=("2025",))


def test_a_run_of_digits_inside_a_word_is_id_shaped() -> None:
    assert _check("Your tag is LT00423.") == IdVerdict(passed=False, unsupported=("00423",))
    assert _check("Your tag is LT00423.", "asset LT-00423").passed


def test_thousands_separators_and_decimals_read_alike_in_the_clause_and_the_evidence() -> None:
    assert _check("About 1,234 users.") == IdVerdict(passed=False, unsupported=("1234",))
    assert _check("About 1,234 users.", "1,234 users signed in").passed
    assert _check("It costs 12.75.", "price: 12.75").passed


def test_a_time_is_never_one_id() -> None:
    """ "8:00" is not 800, nor "16:00" 1600: support hours pass, whatever the evidence says."""
    assert _check("We open at 8:00 and close at 16:00.") == IdVerdict(passed=True)
    assert _check("We open at 8:00 and close at 16:00.", "Support hours: 8 am to 4 pm").passed
    assert _check("Call after 9:30am.").passed
    assert _check("We are open 8:00-16:00.").passed  # no number of one joins the next


def test_a_point_or_a_slash_never_joins_two_numbers() -> None:
    assert _check("It costs 12.75.") == IdVerdict(passed=True)
    assert _check("Support runs 24/7.").passed
    assert _check("It costs 1234.50.") == IdVerdict(passed=False, unsupported=("1234",))
    assert _check("It costs 1,234.50.", "price 1234.50").passed  # its thousands still join


# The hyphens a model writes in a date besides '-': the hyphen, the non-breaking hyphen (which
# the OpenAI family writes), the figure dash, the en dash and the minus sign.
_HYPHENS = ("‐", "‑", "‒", "–", "−")


@pytest.mark.parametrize(
    "clause",
    [
        "It came on 7/11/2026.",
        "It is due 07-11-2026.",
        "Today is 2026-11-07.",
        *(f"It is due 07{hyphen}11{hyphen}2026." for hyphen in _HYPHENS),
        *(f"Today is 2026{hyphen}11{hyphen}07." for hyphen in _HYPHENS),
    ],
)
def test_a_date_around_a_year_is_never_one_id(clause: str) -> None:
    """The prompt's own date ("2026-11-07") among them: the talker may say it back, with any
    hyphen."""
    assert _check(clause) == IdVerdict(passed=True)


@pytest.mark.parametrize("evidence_hyphen", ["-", "‑"])
@pytest.mark.parametrize("hyphen", ["-", *_HYPHENS])
def test_a_tool_results_date_said_back_with_any_hyphen_passes(
    hyphen: str, evidence_hyphen: str
) -> None:
    evidence = '{"created": "2025-10-15", "due": "2026-11-20"}'.replace("-", evidence_hyphen)
    clause = f"It was opened 2025{hyphen}10{hyphen}15 and is due 2026{hyphen}11{hyphen}20."
    assert _check(clause, evidence) == IdVerdict(passed=True)


def test_a_date_in_another_year_still_needs_evidence_for_its_year() -> None:
    assert _check("It came on 7/11/2025.") == IdVerdict(passed=False, unsupported=("2025",))


@pytest.mark.parametrize(
    ("clause", "token"),
    [
        ("Your ticket is 45-21-33.", "452133"),
        ("Your ticket is 11-07-33.", "110733"),  # no year among them
        ("Your ticket is 4521 3390.", "45213390"),
        ("Your ticket is 45-21-2026.", "4521"),  # no day and month: the year only ends it
        ("Your ticket is 45‑21‑33.", "452133"),  # a non-breaking hyphen
        ("Your ticket is 45‑21‑2026.", "4521"),
    ],
)
def test_a_ticket_number_read_in_groups_still_joins(clause: str, token: str) -> None:
    assert _check(clause) == IdVerdict(passed=False, unsupported=(token,))


def test_the_shortest_id_follows_the_setting() -> None:
    four = GuardSettings(min_id_digits=4)
    assert _check("Room 452.", settings=four).passed
    assert not _check("Room 4521.", settings=four).passed


def test_a_declared_pattern_is_id_shaped_and_passes_only_with_evidence() -> None:
    settings = GuardSettings(id_patterns=(r"LT-\d{2}",), min_id_digits=5)
    verdict = _check("Your tag is LT-42.", settings=settings)
    assert verdict == IdVerdict(passed=False, unsupported=("lt 42",))
    assert _check("Your tag is LT-42.", "device lt 42", settings=settings).passed
    assert _check("Your tag is LT-٤٢.", "device LT-42", settings=settings).passed


def test_each_unsupported_token_is_named_once_in_order() -> None:
    verdict = _check("Call 5550 or 7777, not 5550.")
    assert verdict == IdVerdict(passed=False, unsupported=("5550", "7777"))


# The guard's two rules together (`check_clause`): rule A, then rule B, the reason in the
# verdict as `ClauseBlocked` carries it.
_TICKET = "2026110482000123"
_MADE = ActionEvidence(action="create_ticket", texts=(f'{{"ticket_number": "{_TICKET}"}}',))


def _clause(clause: str, *evidence: str, actions: tuple[ActionEvidence, ...] = ()) -> GuardVerdict:
    return check_clause(
        clause,
        evidence=evidence,
        claims={"create_ticket": ("ticket opened",)},
        any_action=default_claims("en"),
        actions=actions,
        settings=SETTINGS,
        year=2026,
    )


def test_a_claim_with_no_record_is_blocked_as_a_claim() -> None:
    verdict = _clause("I've created a ticket for you.")
    assert verdict == GuardVerdict(passed=False, reason="unsupported_claim")
    assert _clause("I've created a ticket for you.", actions=(_MADE,)) == GuardVerdict(
        passed=True, claimed=("create_ticket",)
    )


def test_a_passages_number_in_a_claim_is_blocked_though_rule_b_would_pass_it() -> None:
    fake = "2026110482000999"
    clause = f"Ticket opened, its number is {fake}."
    passage = f"Your ticket number is {fake}."
    assert _check(clause, passage).passed  # rule B alone: the passage is evidence
    verdict = _clause(clause, passage, actions=(_MADE,))
    assert verdict == GuardVerdict(
        passed=False, reason="unsupported_claim", unsupported=(fake,), claimed=("create_ticket",)
    )


def test_the_actions_number_passes_both_rules() -> None:
    """Rule B counts the record's texts as evidence, so what rule A let through it passes."""
    verdict = _clause(f"Ticket opened, number {_TICKET}.", actions=(_MADE,))
    assert verdict == GuardVerdict(passed=True, claimed=("create_ticket",))


def test_a_clause_with_no_claim_is_rule_bs_alone() -> None:
    assert _clause("Your request number is 4521.") == GuardVerdict(
        passed=False, reason="unsupported_id", unsupported=("4521",)
    )
    assert _clause("Your request number is 4521.", '{"request": "4521"}').passed
    assert check_clause(
        "Your request number is 4521.", evidence=(), settings=SETTINGS, year=2026
    ) == GuardVerdict(passed=False, reason="unsupported_id", unsupported=("4521",))


def test_a_claim_phrase_added_in_the_settings_is_a_default_one() -> None:
    settings = GuardSettings.model_validate({"claims": {"en": ["all sorted for you"]}})
    verdict = check_clause(
        "It is all sorted for you.",
        evidence=(),
        any_action=(*default_claims("en"), *settings.claims["en"]),
        settings=settings,
        year=2026,
    )
    assert verdict == GuardVerdict(passed=False, reason="unsupported_claim")
