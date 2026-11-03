"""Speaking numbers and IDs (domain/text/speaking.py): numbers through num2words, IDs digit by
digit from the library's own table, and in a text each run of digits an ID when it has five
digits or more, starts with a zero or follows an ending cue, else a number (plan 003's decision
log). Every text here is written for the test, none taken from an item."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.speaking import speak_digits, speak_id, speak_number
from t2_agentic_voice.languages import speak_id as public_speak_id
from t2_agentic_voice.languages import speak_number as public_speak_number

ARABIC_DIGITS = "صفر واحد اثنان ثلاثة أربعة خمسة ستة سبعة ثمانية تسعة"
ENGLISH_DIGITS = "zero one two three four five six seven eight nine"


def test_the_facade_gives_the_same_functions() -> None:
    assert (public_speak_number, public_speak_id) == (speak_number, speak_id)


@pytest.mark.parametrize(
    ("number", "english", "arabic"),
    [
        (0, "zero", "صفر"),
        (7, "seven", "سبعة"),
        (12, "twelve", "اثنا عشر"),
        (21, "twenty-one", "واحد وعشرون"),
        (300, "three hundred", "ثلاثمائة"),
        (1234, "one thousand two hundred and thirty-four", "ألف ومئتان وأربعة وثلاثون"),
        (-5, "minus five", "سالب خمسة"),
    ],
)
def test_a_number_is_said_in_words_in_each_language(number: int, english: str, arabic: str) -> None:
    assert speak_number(number, language="en") == english
    assert speak_number(number, language="ar") == arabic
    assert speak_number(number, language="ar-SA") == arabic  # both Arabic tags say MSA forms


def test_an_english_number_holds_no_comma_for_the_splitter_to_cut_at() -> None:
    said = speak_number(9_876_543, language="en")
    assert "," not in said
    assert said.startswith("nine million eight hundred and seventy-six thousand")


def test_the_arabic_and_is_joined_to_the_word_after_it() -> None:
    said = speak_number(2345, language="ar")
    assert said == "ألفان وثلاثمائة وخمسة وأربعون"
    assert "و " not in f" {said} "


def test_only_a_whole_number_is_said() -> None:
    with pytest.raises(TypeError, match="whole number"):
        speak_number(2.5, language="en")  # type: ignore[arg-type]


def test_an_id_is_read_digit_by_digit_from_the_library_table() -> None:
    assert speak_id("0123456789", language="en") == ENGLISH_DIGITS
    assert speak_id("0123456789", language="ar") == ARABIC_DIGITS
    assert speak_id("0123456789", language="ar-SA") == ARABIC_DIGITS


def test_an_id_in_arabic_indic_or_persian_digits_reads_the_same() -> None:
    assert speak_id("٠١٢٣٤٥٦٧٨٩", language="ar") == ARABIC_DIGITS
    assert speak_id("۰۱۲۳۴۵۶۷۸۹", language="en") == ENGLISH_DIGITS
    assert speak_id("4٤۴", language="en") == "four four four"


@pytest.mark.parametrize("digits", ["", "12-34", "12 34", "LT9", "²"])
def test_an_id_holds_digits_only(digits: str) -> None:
    with pytest.raises(ValueError, match="digits only"):
        speak_id(digits, language="en")


def test_a_sixteen_digit_ticket_number_is_read_digit_by_digit() -> None:
    english = speak_digits("Your request 2026110300004512 is open.", language="en")
    assert english == (
        "Your request two zero two six one one zero three zero zero zero zero four five one two"
        " is open."
    )
    arabic = speak_digits("طلبك رقم 9081726354453627 مفتوح.", language="ar-SA")
    assert arabic == (
        "طلبك رقم تسعة صفر ثمانية واحد سبعة اثنان ستة ثلاثة خمسة أربعة أربعة خمسة ثلاثة ستة"
        " اثنان سبعة مفتوح."
    )


def test_a_run_of_five_digits_is_an_id() -> None:
    assert speak_digits("code 52341", language="en") == "code five two three four one"


def test_a_run_with_a_leading_zero_is_read_digit_by_digit() -> None:
    assert speak_digits("Desk 042 is free.", language="en") == "Desk zero four two is free."
    assert speak_digits("المكتب 042 متاح.", language="ar") == "المكتب صفر أربعة اثنان متاح."
    assert speak_digits("Desk ٠٧ is free.", language="en") == "Desk zero seven is free."


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (
            "The card ending in 4821 was renewed.",
            "The card ending in four eight two one was renewed.",
        ),
        ("Ending in 3907, it is yours.", "Ending in three nine zero seven, it is yours."),
        ("the one ENDING  IN 1180", "the one ENDING  IN one one eight zero"),
    ],
)
def test_four_digits_after_the_english_cue_are_read_digit_by_digit(text: str, said: str) -> None:
    assert speak_digits(text, language="en") == said


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("البطاقة آخرها 4821 جاهزة", "البطاقة آخرها أربعة ثمانية اثنان واحد جاهزة"),
        ("الطلب ينتهي بـ 3907 اليوم", "الطلب ينتهي بـ ثلاثة تسعة صفر سبعة اليوم"),
        ("الطلب ينتهي ب1180", "الطلب ينتهي ب واحد واحد ثمانية صفر"),
        ("رقمه وينتهي بـ٦٥٤٣", "رقمه وينتهي بـ ستة خمسة أربعة ثلاثة"),
        ("وآخرها 2210", "وآخرها اثنان اثنان واحد صفر"),
    ],
)
def test_four_digits_after_an_arabic_cue_are_read_digit_by_digit(text: str, said: str) -> None:
    assert speak_digits(text, language="ar-SA") == said


def test_a_cue_inside_a_longer_word_is_no_cue() -> None:
    assert speak_digits("pending in 1234", language="en") == (
        "pending in one thousand two hundred and thirty-four"
    )


def test_a_short_run_with_no_cue_is_a_number() -> None:
    assert speak_digits("I have 3 laptops and 1250 cables.", language="en") == (
        "I have three laptops and one thousand two hundred and fifty cables."
    )
    assert speak_digits("عندي 3 أجهزة", language="ar") == "عندي ثلاثة أجهزة"


def test_arabic_indic_digits_are_read_in_a_text() -> None:
    assert speak_digits("عندي ٣ أجهزة و٢١ كابل", language="ar") == (
        "عندي ثلاثة أجهزة و واحد وعشرون كابل"
    )
    assert speak_digits("رقم ٠٥٥١٢", language="ar") == "رقم صفر خمسة خمسة واحد اثنان"


def test_words_are_set_apart_from_a_letter_the_digits_touched() -> None:
    assert speak_digits("T2 and 3D", language="en") == "T two and three D"
    assert speak_digits("tag LT-00423", language="en") == "tag LT-zero zero four two three"


def test_a_text_with_no_digits_is_left_as_it_was() -> None:
    text = "Made-up words, with no digits at all."
    assert speak_digits(text, language="en") == text
    assert speak_digits("", language="ar") == ""
