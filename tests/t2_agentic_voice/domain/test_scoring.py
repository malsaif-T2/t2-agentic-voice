"""term_recall, id_recall and silence_output: one output against its reference, both in the
scorers' form (the canonical normalizer, then the digits), counted so a stratum pools them."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from t2_agentic_voice.domain.recall import Recall
from t2_agentic_voice.domain.scoring import id_recall, scored_form, silence_output, term_recall

TERMS = ["Outlook", "PDF", "Word"]


def recall(expected: int, found: int) -> Recall:
    return Recall(expected=expected, found=found)


def test_the_scored_form_is_the_normalizer_then_the_digits() -> None:
    assert scored_form("أرسل الملف PDF على Outlook!") == "ارسل الملف pdf علي outlook"
    assert scored_form("رقم ١٢٣٤ أو خمسة، سبعة") == "رقم 1234 او 57"
    assert scored_form("  ؟  ") == ""


def test_term_recall_counts_the_terms_the_reference_holds_and_the_output_keeps() -> None:
    reference = "أرسل الملف PDF على Outlook"
    assert term_recall(reference, "ارسل الملف pdf على outlook", TERMS) == recall(2, 2)
    assert term_recall(reference, "ارسل الملف بي دي اف على outlook", TERMS) == recall(2, 1)
    assert term_recall(reference, "", TERMS) == recall(2, 0)
    # "Word" is not in the reference, so the output holding it counts for nothing.
    assert term_recall(reference, "word pdf outlook", TERMS) == recall(2, 2)


def test_a_reference_with_no_term_expects_none() -> None:
    assert term_recall("نعم ارسلها", "نعم ارسلها", TERMS) == recall(0, 0)
    assert term_recall("نعم ارسلها", "Outlook", []) == recall(0, 0)


def test_a_term_counts_once_however_often_it_is_held_or_listed() -> None:
    reference = "PDF ثم PDF ثم pdf"
    assert term_recall(reference, "pdf", ["PDF", "pdf", "P.D.F"]) == recall(1, 1)


def test_a_term_is_held_only_as_a_whole_word() -> None:
    assert term_recall("open Word", "open WordPad", ["Word"]) == recall(1, 0)
    assert term_recall("open Word", "a keyword", ["Word"]) == recall(1, 0)
    assert term_recall("open Word", "باستخدام الword", ["Word"]) == recall(1, 0)


def test_a_term_of_several_words_is_held_whole_and_in_order() -> None:
    terms = ["Microsoft Teams"]
    assert term_recall("افتح Microsoft Teams", "افتح microsoft, teams", terms) == recall(1, 1)
    assert term_recall("افتح Microsoft Teams", "افتح teams microsoft", terms) == recall(1, 0)
    assert term_recall("افتح Microsoft Teams", "افتح microsoft", terms) == recall(1, 0)


def test_terms_and_texts_are_compared_in_the_scored_form() -> None:
    assert term_recall("Office 365", "office ثلاثة ستة خمسة", ["Office 365"]) == recall(1, 1)
    assert term_recall("التذكرة", "التذكره", ["التذكرة"]) == recall(1, 1)


@pytest.mark.parametrize("terms", ["Outlook", "PDF Word"])
def test_a_bare_str_of_terms_is_refused_since_it_would_count_its_letters(terms: str) -> None:
    with pytest.raises(TypeError, match="not one str"):
        term_recall("Outlook", "Outlook", terms)


@pytest.mark.parametrize("terms", [[None], [b"PDF"], ["PDF", 5]])
def test_a_term_that_is_not_a_str_is_refused(terms: Sequence[object]) -> None:
    with pytest.raises(TypeError, match="every term is a str"):
        term_recall("PDF", "PDF", terms)  # type: ignore[arg-type]


@pytest.mark.parametrize("term", ["", "؟", "...", "\u064e"])
def test_a_term_empty_after_normalization_is_refused(term: str) -> None:
    with pytest.raises(ValueError, match="empty after normalization"):
        term_recall("PDF", "PDF", ["PDF", term])


def test_terms_given_as_a_tuple_or_any_sequence_are_read() -> None:
    assert term_recall("PDF Word", "pdf", ("PDF", "Word")) == recall(2, 1)


def test_id_recall_finds_a_ticket_number_however_its_digits_are_said_or_written() -> None:
    reference = "رقم التذكرة 4521"
    for heard in [
        "رقم التذكره 4521",
        "رقم التذكرة ٤٥٢١",
        "رقم التذكرة ۴۵۲۱",
        "رقم التذكرة أربعة خمسة اثنين واحد",
        "the ticket is four five two one",
        "4 5 2 1",
        "4-5-2-1",
        "T-4521",
    ]:
        assert id_recall(reference, heard) == recall(1, 1), heard


def test_an_id_is_compared_whole() -> None:
    reference = "رقم التذكرة 4521"
    for heard in ["4512", "45210", "452", "21 45", "45 و 21", "", "رقم التذكرة"]:
        assert id_recall(reference, heard) == recall(1, 0), heard


def test_a_number_written_in_groups_is_held_as_its_digits_joined() -> None:
    reference = "التذكرة اللي آخرها 4821"
    for heard in [
        "48 21",
        "48-21",
        "4,821",
        "٤٬٨٢١",  # Arabic-Indic digits and the Arabic thousands separator
        "٤٨ ٢١",
        "4 8 21",
        "48.21",  # the normalizer reads a full stop and a slash as a space too
        "48/21",
        "اللي آخرها 48 21 تمام",
    ]:
        assert id_recall(reference, heard) == recall(1, 1), heard


# A made-up number in the shape of an Ole5 ticket number (Q5): the date as YYYYMMDD, then 82,
# then a counter of six digits.
TICKET = "2026110582000731"


@pytest.mark.parametrize(
    "heard",
    [
        TICKET,
        "2026 1105 8200 0731",
        "2026-1105-8200-0731",
        "2,026,110,582,000,731",
        "٢٬٠٢٦٬١١٠٬٥٨٢٬٠٠٠٬٧٣١",
        "٢٠٢٦١١٠٥٨٢٠٠٠٧٣١",
        "٢٠٢٦ ١١٠٥ ٨٢٠٠ ٠٧٣١",
        "two zero two six one one zero five eight two zero zero zero seven three one",
        "اثنين صفر اثنين ستة واحد واحد صفر خمسة ثمانية اثنين صفر صفر صفر سبعة ثلاثة واحد",
        "رقم التذكرة 2026 1105 8200 0731 لو سمحت",
    ],
)
def test_a_ticket_number_is_found_however_it_is_grouped_written_or_said(heard: str) -> None:
    assert id_recall(f"رقم التذكرة {TICKET}", heard) == recall(1, 1)


@pytest.mark.parametrize(
    "heard",
    [
        "2026 1105 8200",  # a part of it
        "1105 8200 0731",
        "202611058200073",
        "0731 8200 1105 2026",  # its groups in another order
        "8200 0731 2026 1105",
        "2026 1105 يعني 8200 0731",  # a word between its groups
        "2026 1105 then 8200 0731",
    ],
)
def test_a_ticket_number_in_part_out_of_order_or_split_by_a_word_is_missed(heard: str) -> None:
    assert id_recall(f"رقم التذكرة {TICKET}", heard) == recall(1, 0)


def test_an_id_expected_twice_is_found_twice_only_when_held_twice() -> None:
    assert id_recall("4821 ثم 4821", "48 21") == recall(2, 1)
    assert id_recall("4821 ثم 4821", "48 21 48 21") == recall(2, 2)
    assert id_recall("4821 ثم 4821", "48-21 and 4821") == recall(2, 2)
    assert id_recall("4821", "48 21 48 21") == recall(1, 1)
    twice = f"{TICKET} يعني {TICKET}"
    assert id_recall(twice, "2026 1105 8200 0731") == recall(2, 1)
    assert id_recall(twice, "2026 1105 8200 0731 2026 1105 8200 0731") == recall(2, 2)


def test_no_digit_of_the_output_counts_for_two_ids() -> None:
    both = f"رقم التذكرة {TICKET} اللي آخرها 0731"
    assert id_recall(both, "2026 1105 8200 0731") == recall(2, 1)
    assert id_recall(both, "2026 1105 8200 0731 اللي آخرها 0731") == recall(2, 2)
    assert id_recall(both, "0731 يعني 2026 1105 8200 0731") == recall(2, 2)
    # At each group the longest ID that starts there is taken, so the year is not taken out of
    # the ticket number.
    assert id_recall(f"{TICKET} من 2026", "2026 1105 8200 0731 من 2026") == recall(2, 2)


def test_a_last_four_id_keeps_its_leading_zero() -> None:
    reference = "التذكرة اللي آخرها 0731"
    for heard in ["0731", "07 31", "0 7 3 1", "zero seven three one", "صفر سبعة ثلاثة واحد"]:
        assert id_recall(reference, heard) == recall(1, 1), heard
    for heard in ["731", "7 31", "73 1"]:
        assert id_recall(reference, heard) == recall(1, 0), heard


def test_an_id_spoken_by_the_reference_one_digit_at_a_time_is_one_id() -> None:
    assert id_recall("خمسة سبعة اثنين", "572") == recall(1, 1)


def test_every_id_counts_and_a_repeated_one_counts_as_often_as_it_is_held() -> None:
    assert id_recall("4521 و 7788", "7788") == recall(2, 1)
    assert id_recall("4521 ثم 4521", "4521") == recall(2, 1)
    assert id_recall("4521 ثم 4521", "4521 4521") == recall(2, 2)
    assert id_recall("4521 ثم 4521", "4521 and 4521") == recall(2, 2)
    assert id_recall("4521", "4521 and 4521") == recall(1, 1)


def test_digits_inside_a_word_are_an_id_too() -> None:
    assert id_recall("T-1234", "t1234") == recall(1, 1)


def test_digits_inside_a_word_join_no_neighbour() -> None:
    assert id_recall("4821", "t48 21") == recall(1, 0)
    assert id_recall("4821", "48 21t") == recall(1, 0)


def test_a_reference_with_no_digit_expects_no_id() -> None:
    assert id_recall("نعم ارسلها", "1234") == recall(0, 0)


@pytest.mark.parametrize(
    ("output", "characters"),
    [
        ("", 0),
        ("   ", 0),
        ("؟!.", 0),
        ("\u200f\u200b", 0),  # invisible marks only
        ("شكرا", 4),
        ("ش\u064fك\u0652ر\u064bا.", 4),  # diacritics and punctuation are not text
        ("Thank you.", 8),  # spaces are not text either
        ("five", 4),  # a digit's name counts its letters, as produced
        ("one two three", 11),
        ("واحد", 4),
        ("١٢٣", 3),
    ],
)
def test_silence_output_counts_the_characters_produced(output: str, characters: int) -> None:
    assert silence_output(output) == characters
