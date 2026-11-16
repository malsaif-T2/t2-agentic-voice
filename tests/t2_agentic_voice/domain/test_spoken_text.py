"""A text's times, dates and numbers said by register (domain/text/spoken_text.py), what the
`tts.spoken_numbers` setting's `by_register` says once the output guard has read the digits.
Every text here is written for the test."""

from __future__ import annotations

import pytest
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
