"""The output guard's ID rule (domain/guard.py, the design's 8.2 rule B): every ID-shaped token
of a clause needs evidence seen this call, after digits are normalized (Arabic-Indic and Persian
digits, digit words, digits in groups); the current year and the next pass with none; declared
patterns are ID-shaped too. Every number here is made up for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.guard import IdVerdict, check_ids

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
