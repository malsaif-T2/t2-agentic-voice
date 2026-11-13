"""normalize_arabic: the prototype's normalizer, ported rule for rule (D-010), checked against
the characterization table, and the spelling guide's rulings on comparing texts (plan
002, Q8: "Use these rules")."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import normalize_digits

TABLE = Path(__file__).parents[1] / "fixtures" / "arabic_normalizer_characterization.json"
ROWS: list[dict[str, Any]] = json.loads(TABLE.read_text(encoding="utf-8"))["rows"]
GAPS = [row for row in ROWS if "gap" in row]
GUIDE_VERDICT = re.compile(r"the guide's verdict string is (\S+) \(Q8\)")


def verdict_form(text: str) -> str:
    """What the verdict compares: both normalizations, then every space removed."""
    return normalize_digits(normalize_arabic(text)).replace(" ", "")


@pytest.mark.parametrize("row", ROWS, ids=[row["note"] for row in ROWS])
def test_each_row_normalizes_as_the_prototype_did(row: dict[str, Any]) -> None:
    assert normalize_arabic(row["input"]) == row["normalize"]


@pytest.mark.parametrize("row", ROWS, ids=[row["note"] for row in ROWS])
def test_each_row_is_compared_as_the_prototype_compared_it_but_where_the_guide_rules(
    row: dict[str, Any],
) -> None:
    if "gap" in row:
        found = GUIDE_VERDICT.search(row["note"])
        assert found is not None, row
        assert verdict_form(row["input"]) == found.group(1)
    else:
        assert verdict_form(row["input"]) == row["norm"]


def test_the_table_holds_the_two_gaps_the_guide_rules_on_and_each_departs_from_the_prototype() -> (
    None
):
    assert [row["input"] for row in GAPS] == ["خمسة سبعة", "five seven"]
    for row in GAPS:
        assert verdict_form(row["input"]) != row["norm"]


def test_the_prototype_own_normalizer_test_still_holds() -> None:
    # Ole5-chatbot/tests/test_voice_rules.py, lines 10-14, read as text (D-010).
    assert normalize_arabic("ت\u064eم\u064eام\u064f!") == "تمام"
    assert normalize_arabic("أرسلـــها، الآن.") == "ارسلها الان"
    assert normalize_arabic("التذكرة") == normalize_arabic("التذكره")
    assert normalize_arabic("  Yes,   SUBMIT. ") == "yes submit"


@pytest.mark.parametrize("row", ROWS, ids=[row["note"] for row in ROWS])
def test_normalizing_twice_changes_nothing(row: dict[str, Any]) -> None:
    once = normalize_arabic(row["input"])
    assert normalize_arabic(once) == once


@pytest.mark.parametrize(
    ("written", "folded"),
    [
        ("أ", "ا"),  # alef with hamza above
        ("إ", "ا"),  # alef with hamza below
        ("آ", "ا"),  # alef with madda above
        ("ة", "ه"),  # teh marbuta
        ("ى", "ي"),  # alef maksura
        ("ؤ", "و"),  # waw with hamza above
        ("ئ", "ي"),  # yeh with hamza above
    ],
)
def test_q8_folds_the_prototype_letter_forms(written: str, folded: str) -> None:
    assert normalize_arabic(f"ب{written}ب") == f"ب{folded}ب"


@pytest.mark.parametrize("kept", ["ٱ", "ی", "ک", "ء", "ه", "ي", "ا"])
def test_q8_keeps_every_other_letter_form(kept: str) -> None:
    assert normalize_arabic(f"ب{kept}ب") == f"ب{kept}ب"


@pytest.mark.parametrize(
    "mark",
    ["\u064b", "\u064c", "\u064d", "\u064e", "\u064f", "\u0650", "\u0651", "\u0652", "\u0670"],
)
def test_q8_drops_every_diacritic(mark: str) -> None:
    assert normalize_arabic(f"كت{mark}اب") == "كتاب"


def test_q8_drops_the_tatweel_however_long() -> None:
    assert normalize_arabic("تمـــــام") == normalize_arabic("تمام") == "تمام"


def test_q8_reads_english_in_lower_case() -> None:
    assert normalize_arabic("PDF Outlook WORD") == "pdf outlook word"


@pytest.mark.parametrize("mark", list("،؛؟!?.,:;\"'()[]{}«»-–—…/\\*&%$#@+=<>|~^`"))
def test_q8_ignores_punctuation_in_every_script(mark: str) -> None:
    assert normalize_arabic(f"نعم{mark}ارسل") == "نعم ارسل"
    assert verdict_form(f"نعم{mark}ارسل") == verdict_form("نعم ارسل")


def test_q8_ignores_spaces_in_the_verdict_so_two_words_written_as_one_still_count() -> None:
    assert verdict_form("لو سمحت") == verdict_form("لوسمحت")
    assert verdict_form("Out look") == verdict_form("Outlook")


def test_q8_keeps_an_english_contraction_as_said() -> None:
    assert verdict_form("Don't") == verdict_form("don’t") == "dont"
    assert verdict_form("don't") != verdict_form("do not")


@pytest.mark.parametrize(
    "space", [" ", "\t", "\n", "\r\n", "\u00a0", "\u2003", "\u3000", "\u2028", " \t \n "]
)
def test_every_kind_of_space_is_one_space(space: str) -> None:
    assert normalize_arabic(f"{space}وقف{space}وقف{space}") == "وقف وقف"


@pytest.mark.parametrize(
    "mark",
    [
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u061c",  # Arabic letter mark
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\ufeff",  # byte-order mark
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u2066",  # left-to-right isolate
    ],
)
def test_an_invisible_format_character_never_changes_the_verdict(mark: str) -> None:
    # A provider (or a pasted reference) may carry bidirectional or zero-width characters that
    # no one sees; each reads as a space, so the verdict, which drops spaces, is unchanged.
    for text in ["لو سمحت", "ارسل الملف pdf"]:
        marked = mark + text.replace(" ", mark + " ") + mark
        assert normalize_arabic(marked) == normalize_arabic(text)
    assert verdict_form(f"لو{mark}سمحت") == verdict_form("لوسمحت")


def test_a_combining_mark_outside_the_arabic_marks_reads_as_a_space_as_in_the_prototype() -> None:
    # The prototype has no Unicode composition step: a precomposed é is a letter, while e and a
    # combining acute accent are a letter and a non-word character.
    assert normalize_arabic("café") == "café"
    assert normalize_arabic("cafe\u0301") == "cafe"


def test_an_emoji_or_a_symbol_is_dropped_like_punctuation() -> None:
    assert normalize_arabic("تمام 👍🏽 ✔ © ™") == "تمام"


def test_digits_are_kept_as_written_for_normalize_digits() -> None:
    assert normalize_arabic("رقم ١٢٣٤ و ۱۲ و 7") == "رقم ١٢٣٤ و ۱۲ و 7"


def test_a_long_text_normalizes_whole() -> None:
    text = "أرسلـــها، الآن. " * 20_000
    assert normalize_arabic(text) == " ".join(["ارسلها الان"] * 20_000)


def test_nothing_but_marks_and_punctuation_is_empty() -> None:
    assert normalize_arabic("\u064e\u0651ـ؟! \u200f…") == ""
