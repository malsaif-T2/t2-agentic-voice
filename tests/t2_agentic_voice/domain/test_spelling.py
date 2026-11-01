"""spelling_issues: where a reference breaks a team's spelling guide, the guide given as data.
The rulings below are written as a team writes its guide, after the kinds the owner ruled on
for Ole5's (plan 002, Q8: "Use these rules"): product terms in Latin script, numbers as digits,
listening sounds from a fixed list."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.domain.text.rulings import SpellingIssue, SpellingRule
from t2_agentic_voice.domain.text.spelling import spelling_issues

SAID = {"said": "Use these rules", "on": "2026-11-01"}


def rule(rule_id: str, avoid: list[str], write: str) -> SpellingRule:
    return SpellingRule.model_validate({"id": rule_id, "avoid": avoid, "write": write} | SAID)


OUTLOOK = rule("product-term-outlook", ["اوتلوك", "أوتلوك", "out look"], "Outlook")
PDF = rule("product-term-pdf", ["بي دي اف", "بي دي إف"], "PDF")
FIVE = rule("number-five", ["خمسة", "five"], "5")
LISTENING = rule("listening-aha", ["اهاا", "ahaa"], "اها")
MM_HMM = rule("listening-mm-hmm", ["mhm", "mmhmm"], "mm-hmm")
GUIDE = [OUTLOOK, PDF, FIVE, LISTENING, MM_HMM]


def issue(of: SpellingRule, found: str) -> SpellingIssue:
    return SpellingIssue(rule=of.id, found=found, write=of.write)


def test_a_reference_that_follows_the_guide_has_no_issue() -> None:
    for reference in [
        "أرسل الملف PDF على Outlook",
        "رقم التذكرة 5",
        "اها",
        "mm-hmm",
        "",
    ]:
        assert spelling_issues(reference, GUIDE) == []


def test_q8_a_product_term_in_arabic_script_is_an_issue() -> None:
    assert spelling_issues("أرسل الملف على أوتلوك", GUIDE) == [issue(OUTLOOK, "اوتلوك")]
    assert spelling_issues("ملف بي دي إف", GUIDE) == [issue(PDF, "بي دي اف")]


def test_q8_a_number_written_as_a_word_is_an_issue() -> None:
    assert spelling_issues("ابغى خمسة تذاكر", GUIDE) == [issue(FIVE, "خمسة")]
    assert spelling_issues("I need Five.", GUIDE) == [issue(FIVE, "five")]


def test_q8_a_listening_sound_off_the_fixed_list_is_an_issue() -> None:
    assert spelling_issues("اهاا", GUIDE) == [issue(LISTENING, "اهاا")]
    assert spelling_issues("Mhm.", GUIDE) == [issue(MM_HMM, "mhm")]


def test_spellings_are_compared_after_the_normalizer() -> None:
    # Diacritics, tatweel, letter forms, case and punctuation do not hide an avoided spelling.
    for written in ["أ\u064eوتلوك", "اوتـــلوك", "آوتلوك؟", "إوتلوك"]:
        assert spelling_issues(f"على {written}", [OUTLOOK]) == [issue(OUTLOOK, "اوتلوك")]
    assert spelling_issues("send it on OUT-LOOK", [OUTLOOK]) == [issue(OUTLOOK, "out look")]


def test_a_spelling_inside_a_longer_word_is_not_an_issue() -> None:
    assert spelling_issues("fiver, fivefold, fives", [FIVE]) == []
    assert spelling_issues("الخمسة", [FIVE]) == []
    assert spelling_issues("على الإيميل وأوتلوك", [OUTLOOK]) == []  # with a prefix, one word


def test_a_phrase_matches_only_whole_and_in_order() -> None:
    assert spelling_issues("بي دي", [PDF]) == []
    assert spelling_issues("اف دي بي", [PDF]) == []
    assert spelling_issues("الملف بي دي اف كامل", [PDF]) == [issue(PDF, "بي دي اف")]


def test_one_issue_per_avoided_spelling_however_often_it_is_held() -> None:
    reference = "أوتلوك ثم أوتلوك ثم out look ثم خمسة"
    assert spelling_issues(reference, GUIDE) == [
        issue(OUTLOOK, "اوتلوك"),  # the first of the rule's spellings that normalize alike
        issue(OUTLOOK, "out look"),
        issue(FIVE, "خمسة"),
    ]


def test_issues_follow_the_order_of_the_rules_and_of_their_spellings() -> None:
    reference = "five خمسة أوتلوك"
    assert spelling_issues(reference, [FIVE, OUTLOOK]) == [
        issue(FIVE, "خمسة"),
        issue(FIVE, "five"),
        issue(OUTLOOK, "اوتلوك"),
    ]
    assert [i.rule for i in spelling_issues(reference, [OUTLOOK, FIVE])] == [
        OUTLOOK.id,
        FIVE.id,
        FIVE.id,
    ]


def test_a_ruling_that_drops_a_spelling_says_to_write_nothing() -> None:
    filler = rule("no-filler", ["يعني"], "")
    assert spelling_issues("ابغى يعني تذكرة", [filler]) == [issue(filler, "يعني")]


def test_no_rules_no_issues() -> None:
    assert spelling_issues("أوتلوك", []) == []


@pytest.mark.parametrize(
    ("reference", "held"),
    [
        ("aXb", False),  # "a.b" is a phrase of two words, never a pattern
        ("a b", True),
        ("aab", False),
        ("a-b", True),
    ],
)
def test_an_avoided_spelling_is_text_never_a_pattern(reference: str, held: bool) -> None:
    dotted = rule("dotted", ["a.b"], "ab")
    assert (spelling_issues(reference, [dotted]) != []) is held


@pytest.mark.parametrize("avoid", ["؟!", "...", "\u064e", "ـــ", "  "])
def test_a_spelling_empty_after_normalization_is_refused_since_none_could_hold_it(
    avoid: str,
) -> None:
    broken = rule("never-found", ["اوتلوك", avoid], "Outlook")
    with pytest.raises(ValueError, match="'never-found' avoids a spelling that is empty"):
        spelling_issues("anything at all", [broken])


@pytest.mark.parametrize(
    ("avoid", "write"),
    [
        ("pdf", "PDF"),  # case is folded before comparing, so case cannot be ruled on
        ("التذكره", "التذكرة"),  # nor can the letter forms the normalizer folds
        ("word", "Word document"),  # what to write holds it
    ],
)
def test_a_ruling_that_its_own_spelling_would_break_is_refused(avoid: str, write: str) -> None:
    broken = rule("self-breaking", [avoid], write)
    with pytest.raises(ValueError, match="'self-breaking' avoids a spelling that what it says"):
        spelling_issues("a reference that holds none of it", [broken])


def test_a_broken_ruling_is_refused_after_rulings_that_found_issues() -> None:
    broken = rule("never-found", ["!"], "x")
    with pytest.raises(ValueError, match="never-found"):
        spelling_issues("أوتلوك", [OUTLOOK, broken])


def test_a_guide_read_from_data_as_a_team_writes_it() -> None:
    data: list[dict[str, Any]] = [
        {"id": "product-term-word", "avoid": ["وورد"], "write": "Word"} | SAID,
        {"id": "number-seven", "avoid": ["سبعة"], "write": "7"} | SAID,
    ]
    guide = [SpellingRule.model_validate(entry) for entry in data]
    assert spelling_issues("افتح وورد واكتب سبعة", guide) == [
        SpellingIssue(rule="product-term-word", found="وورد", write="Word"),
        SpellingIssue(rule="number-seven", found="سبعة", write="7"),
    ]
