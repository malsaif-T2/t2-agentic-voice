"""normalize_digits: Arabic-Indic and Persian digits as ASCII (the prototype's scorer, D-010),
and digits said one word each, in Arabic and in English, as those digits (the spelling guide,
plan 002, Q8: "digits said one by one count as those digits")."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.digits import normalize_digits

# Each digit's names as a speaker's words reach a transcript, in the forms the normalizer folds
# and in the folded forms themselves.
ARABIC_NAMES = [
    ("صفر", "0"),
    ("واحد", "1"),
    ("اثنين", "2"),
    ("إثنين", "2"),
    ("اثنان", "2"),
    ("ثلاثة", "3"),
    ("ثلاثه", "3"),
    ("أربعة", "4"),
    ("اربعه", "4"),
    ("خمسة", "5"),
    ("خمسه", "5"),
    ("ستة", "6"),
    ("سبعة", "7"),
    ("ثمانية", "8"),
    ("ثمانيه", "8"),
    ("تسعة", "9"),
]
ENGLISH_NAMES = [
    ("zero", "0"),
    ("one", "1"),
    ("two", "2"),
    ("three", "3"),
    ("four", "4"),
    ("five", "5"),
    ("six", "6"),
    ("seven", "7"),
    ("eight", "8"),
    ("nine", "9"),
]


def both(text: str) -> str:
    """The scorers' order: the canonical normalizer first, then the digits."""
    return normalize_digits(normalize_arabic(text))


def test_arabic_indic_digits_read_as_ascii() -> None:
    assert normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"


def test_persian_digits_read_as_ascii() -> None:
    assert normalize_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"


def test_a_digit_character_is_read_wherever_it_stands() -> None:
    assert normalize_digits("T-٤٥۶٧ و رقم٨") == "T-4567 و رقم8"


@pytest.mark.parametrize(("name", "digit"), ARABIC_NAMES)
def test_a_digit_said_as_one_arabic_word_is_that_digit(name: str, digit: str) -> None:
    assert normalize_digits(name) == digit
    assert both(f"رقم {name}") == f"رقم {digit}"


@pytest.mark.parametrize(("name", "digit"), ENGLISH_NAMES)
def test_a_digit_said_as_one_english_word_is_that_digit(name: str, digit: str) -> None:
    assert normalize_digits(name) == normalize_digits(name.upper()) == digit
    assert both(f"Ticket {name.title()}.") == f"ticket {digit}"


def test_a_name_written_with_diacritics_or_tatweel_is_read_after_the_normalizer() -> None:
    assert both("خ\u064eم\u0652س\u064eة سـبـعـة") == "57"


@pytest.mark.parametrize(
    ("said", "read"),
    [
        ("خمسة سبعة", "57"),  # the guide's own example (Q8)
        ("five seven", "57"),
        ("أربعة خمسة اثنين واحد", "4521"),  # the design's 8.2 example
        ("four five two one", "4521"),
        ("4 5 2 1", "4521"),  # digits written one at a time, as said
        ("٤ ٥ ۲ 1", "4521"),
        ("خمسة 7 two", "572"),  # names and digits in one run
        ("Five  \t Seven", "57"),
    ],
)
def test_digits_said_one_at_a_time_are_one_number(said: str, read: str) -> None:
    assert normalize_digits(said) == read
    assert both(said) == read


def test_a_run_ends_at_any_other_word() -> None:
    assert normalize_digits("رقم خمسة سبعة لو سمحت ثلاثة") == "رقم 57 لو سمحت 3"
    assert normalize_digits("one two and three four") == "12 and 34"


def test_numbers_of_more_than_one_digit_stay_apart() -> None:
    assert normalize_digits("45 21") == "45 21"
    assert normalize_digits("2026 5 7") == "2026 57"
    assert normalize_digits("5 7 2026") == "57 2026"


def test_punctuation_ends_a_run_until_the_normalizer_reads_it_as_a_space() -> None:
    assert normalize_digits("5, 7") == "5, 7"
    assert normalize_digits("five-seven") == "5-7"
    assert both("5, 7") == both("five-seven") == "57"


def test_the_text_around_the_digits_is_left_as_it_is() -> None:
    assert normalize_digits("  Five  apples,\nOne pear!  ") == "  5  apples,\n1 pear!  "


@pytest.mark.parametrize(
    "word",
    [
        "someone",  # holds "one"
        "fives",
        "Seventy",
        "twenty",  # a number word: not a digit's name
        "الخميس",  # Thursday, which holds the letters of five
        "وخمسة",  # "and five": a name with a prefix is another word
        "خمس",  # the short forms are also everyday words
        "سبع",
        "تسع",
        "ست",
        "واحدة",
    ],
)
def test_a_word_that_is_not_a_digit_name_on_its_own_is_kept(word: str) -> None:
    assert normalize_digits(word) == word
    assert normalize_digits(f"5 {word} 7") == f"5 {word} 7"


def test_a_number_said_as_number_words_is_not_composed() -> None:
    # Only digits one at a time: "twenty-one" is a number word and a digit's name.
    assert both("twenty-one") == "twenty 1"


def test_other_scripts_digits_are_not_read() -> None:
    # Devanagari five, a superscript two and a circled three: not in the spelling guide.
    assert normalize_digits("५ ² ③") == "५ ² ③"


def test_normalizing_twice_changes_nothing() -> None:
    for text in ["خمسة سبعة", "4 5 2 1", "رقم ١٢ و ٣٤", "one two and three", ""]:
        once = normalize_digits(text)
        assert normalize_digits(once) == once


def test_nothing_in_nothing_out() -> None:
    assert normalize_digits("") == ""
    assert normalize_digits("   ") == "   "


def test_a_long_run_of_names_reads_whole() -> None:
    said = " ".join(["خمسة", "seven", "٢"] * 10_000)
    assert normalize_digits(said) == "572" * 10_000
