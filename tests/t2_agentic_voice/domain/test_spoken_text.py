"""A text's times, dates and numbers said by register (domain/text/spoken_text.py), what the
`tts.spoken_numbers` setting's `by_register` says once the output guard has read the digits.
Every text here is written for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.text.arabic_numbers import Register
from t2_agentic_voice.domain.text.speaking import speak_digits
from t2_agentic_voice.domain.text.spoken_text import speak_text


def test_a_time_and_an_amount_are_said_in_the_saudi_register() -> None:
    said = speak_text("رحلة 09:10 بـ 2450 ريال", language="ar-SA", register="saudi")
    assert said == "رحلة تسع وعشر دقايق الصبح بـ ألفين وأربع مية وخمسين ريال"


def test_an_ar_sa_reply_to_an_msa_caller_is_said_in_msa() -> None:
    said = speak_text("الرحلة 16:00 بـ 2450 ريال", language="ar-SA", register="msa")
    assert said == "الرحلة الرابعة عصرًا بـ ألفان وأربعمئة وخمسون ريال"


def test_with_no_register_the_tag_chooses_it() -> None:
    assert speak_text("21:30", language="ar-SA") == "تسع ونص بالليل"
    assert speak_text("21:30", language="ar") == "التاسعة والنصف مساءً"


def test_an_english_reply_has_one_form_and_keeps_num2words_numbers() -> None:
    said = speak_text("The 09:10 at 2450 riyals.", language="en", register="saudi")
    assert said == "The nine ten in the morning at two thousand four hundred and fifty riyals."


def test_an_amount_whose_thousands_a_space_parts_is_one_number() -> None:
    # Run F's f09 (f-dev-lean-4): "total 3 080." was said "three zero eight zero".
    for gap in (" ", "\u00a0", "\u2009", "\u202f"):
        said = speak_text(f"total 3{gap}080.", language="en")
        assert said == "total three thousand and eighty.", repr(gap)
    # f26 and f07 (riyals after it); al-majmuu' (the total); bi-3080 riyaal (for 3080 riyals)
    cases: list[tuple[str, str, LanguageTag]] = [
        ("the total is 5 140 SAR.", "the total is 5140 SAR.", "en"),
        ("the 5th at 1 140 riyals", "the 5th at 1140 riyals", "en"),
        ("flight T2 102 at 1 140 riyals", "flight T2 102 at 1140 riyals", "en"),
        ("المجموع 3 080", "المجموع 3080", "ar-SA"),
        ("بـ 3 080 ريال", "بـ 3080 ريال", "ar"),
    ]
    for spaced, whole, tag in cases:
        assert speak_text(spaced, language=tag) == speak_text(whole, language=tag), spaced


@pytest.mark.parametrize("language", ["en", "ar-SA", "ar"])
@pytest.mark.parametrize(
    "text",
    [
        "T2 401",  # a flight's name as the tools write it, never "T two thousand four hundred"
        "your flight is T2 102.",
        "the reference is 482 913.",  # a reference read in groups, beside no amount
        "flights 101 102",  # two numbers side by side
        "total 1 234 567",  # more than one group
        "call 800 123 456",
        "050 123 4567",  # a leading zero
        "total 3 0800",  # a group of four
    ],
)
def test_a_space_before_three_digits_parts_no_thousands_outside_an_amount(
    text: str, language: LanguageTag
) -> None:
    # Read as before: each run of digits on its own, in the tag's register.
    register: Register | None = {"en": None, "ar-SA": "saudi", "ar": "msa"}[language]
    said = speak_digits(text, language=language, register=register)
    assert speak_text(text, language=language) == said


def test_a_time_before_three_digits_is_said_as_a_time() -> None:
    said = speak_text("at 09:10 219 riyals", language="en")
    assert said == "at nine ten in the morning two hundred and nineteen riyals"


def test_an_iso_date_is_said_with_its_weekday_never_its_year() -> None:
    assert speak_text("يوم 2026-12-17", language="ar-SA") == "يوم الخميس سبعطعش ديسمبر"
    assert speak_text("on 2026-12-17", language="en") == "on Thursday the seventeenth of December"


def test_the_part_of_the_day_said_right_after_a_time_is_not_said_twice() -> None:
    assert speak_text("09:10 الصبح", language="ar-SA") == "تسع وعشر دقايق الصبح"
    assert speak_text("at 21:30 in the evening", language="en") == ("at nine thirty in the evening")


@pytest.mark.parametrize("text", ["25:10", "10:75", "2026-02-30", "10:30:15", "1:2:3"])
def test_what_is_no_time_or_date_is_read_as_the_speaking_rules_read_it(text: str) -> None:
    assert speak_text(text, language="en") == speak_digits(text, language="en")


def test_arabic_indic_digits_are_read_as_a_time() -> None:
    assert speak_text("٠٩:١٠", language="ar-SA") == "تسع وعشر دقايق الصبح"


def test_an_id_is_still_read_digit_by_digit() -> None:
    said = speak_text("حجزك 50912", language="ar-SA", register="saudi")
    assert said == speak_digits("حجزك 50912", language="ar-SA")
