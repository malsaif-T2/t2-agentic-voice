"""The words the app's own lines say numbers, times, dates, amounts and the travelers in
(flight_voice/said/numbers.py), in Saudi Arabic, MSA and English: the forms of the build spec's
table, every departure time of the timetable and every day of a month said with no digit, each
time with its own part of the day, and an amount's noun in the case its number takes."""

from __future__ import annotations

import re
from datetime import date, time, timedelta

import pytest
from flight_voice.airline.airports import AIRPORTS, HOME, REGISTERS, Register
from flight_voice.airline.schedule import flights
from flight_voice.said import words
from flight_voice.said.numbers import (
    speak_amount,
    speak_date,
    speak_number,
    speak_time,
    speak_travelers,
)

DEC_17 = date(2026, 12, 17)


@pytest.mark.parametrize(
    ("register", "said"),
    [
        ("saudi", "تسع وعشر دقايق الصبح"),
        ("msa", "التاسعة وعشر دقائق صباحًا"),
        ("en", "nine ten in the morning"),
    ],
)
def test_a_morning_departure_is_said_with_its_part_of_the_day(
    register: Register, said: str
) -> None:
    assert speak_time(time(9, 10), register) == said


def test_the_forms_of_the_spec_s_table() -> None:
    assert speak_time(time(16, 0), "saudi") == "أربع العصر"
    assert speak_time(time(16, 0), "msa") == "الرابعة عصرًا"
    assert speak_time(time(16, 0), "en") == "four in the afternoon"
    assert speak_time(time(21, 30), "saudi") == "تسع ونص بالليل"
    assert speak_time(time(21, 30), "msa") == "التاسعة والنصف مساءً"
    # English says 18:00 to 21:59 "in the evening", as the replies' words do (words.py).
    assert speak_time(time(21, 30), "en") == "nine thirty in the evening"
    assert speak_date(DEC_17, "saudi") == "الخميس سبعطعش ديسمبر"
    assert speak_date(DEC_17, "msa") == "الخميس السابع عشر من ديسمبر"
    assert speak_date(DEC_17, "en") == "Thursday the seventeenth of December"
    assert speak_amount(2450, "saudi") == "ألفين وأربع مية وخمسين ريال"
    assert speak_amount(2450, "msa") == "ألفان وأربعمئة وخمسون ريالًا"
    assert speak_amount(5120, "saudi") == "خمسة آلاف ومية وعشرين ريال"
    assert speak_amount(5120, "msa") == "خمسة آلاف ومئة وعشرون ريالًا"
    assert speak_amount(5120, "en") == "five thousand one hundred and twenty riyals"


def test_the_travelers_are_said_as_the_read_back_says_them() -> None:
    assert [speak_travelers(n, "saudi") for n in (1, 2, 3)] == [
        "لك أنت",
        "لك ولشخص ثاني",
        "لثلاثة أشخاص",
    ]
    assert [speak_travelers(n, "msa") for n in (1, 2, 3)] == ["لك وحدك", "لشخصين", "لثلاثة أشخاص"]
    assert [speak_travelers(n, "en") for n in (1, 2, 9)] == [
        "you",
        "two travelers",
        "nine travelers",
    ]
    for register in REGISTERS:
        said = [speak_travelers(n, register) for n in range(1, 10)]
        assert len(set(said)) == 9 and not any(re.search(r"\d", s) for s in said)


def test_saudi_and_msa_numbers_take_their_own_forms() -> None:
    saudi = {11: "احدعش", 17: "سبعطعش", 25: "خمسة وعشرين", 200: "ميتين", 3000: "ثلاثة آلاف"}
    msa = {11: "أحد عشر", 17: "سبعة عشر", 25: "خمسة وعشرون", 200: "مئتان", 3000: "ثلاثة آلاف"}
    assert {n: speak_number(n, "saudi") for n in saudi} == saudi
    assert {n: speak_number(n, "msa") for n in msa} == msa
    assert speak_number(13480, "msa") == "ثلاثة عشر ألفًا وأربعمئة وثمانون"
    assert speak_number(13480, "saudi") == "ثلطعش ألف وأربع مية وثمانين"
    assert speak_number(200000, "msa") == "مئتا ألف"
    assert speak_number(0, "saudi") == "صفر"
    for register in REGISTERS:
        with pytest.raises(ValueError, match="999 999"):
            speak_number(1_000_000, register)


def test_every_number_up_to_a_large_total_is_words_alone() -> None:
    for register in REGISTERS:
        for n in (*range(1, 1200), *range(1200, 250_000, 370)):
            said = speak_number(n, register)
            assert said and not re.search(r"\d", said), (register, n)
            assert "  " not in said and not said.startswith(" و"), (register, n)


def test_an_amount_s_noun_takes_its_number_s_case() -> None:
    assert speak_amount(5110, "saudi").endswith(" ريالات")
    assert speak_amount(5110, "msa").endswith(" ريالات")
    assert speak_amount(5100, "msa").endswith(" ريال")
    assert speak_amount(5180, "msa").endswith(" ريالًا")
    assert speak_amount(5180, "saudi").endswith(" ريال")


def _times() -> set[time]:
    found: set[time] = set()
    for code in AIRPORTS:
        if code != HOME:
            found |= {f.departs for f in (*flights(HOME, code), *flights(code, HOME))}
    return found


def test_every_departure_of_the_timetable_is_said_in_words_with_its_part_of_the_day() -> None:
    times = _times()
    assert len(times) > 30
    for register in REGISTERS:
        said = {at: speak_time(at, register) for at in times}
        assert len(set(said.values())) == len(times), register
        for at, text in said.items():
            assert not re.search(r"\d", text), (register, at)
            assert text.endswith(words.part_said(at, register)), (register, at)


def test_a_quarter_to_is_of_the_hour_to_come_and_keeps_its_own_part_of_the_day() -> None:
    assert speak_time(time(15, 45), "saudi") == "أربع إلا ربع العصر"
    assert speak_time(time(15, 45), "msa") == "الرابعة إلا ربعًا عصرًا"
    assert speak_time(time(23, 55), "saudi") == "اثنعش إلا خمس بالليل"
    assert speak_time(time(11, 50), "saudi") == "اثنعش إلا عشر الصبح"
    assert speak_time(time(17, 5), "en") == "five oh five in the afternoon"
    assert speak_time(time(0, 25), "en") == "twelve twenty-five at night"


def test_every_day_of_a_month_is_said_with_its_weekday_in_words() -> None:
    first = date(2026, 12, 1)
    for register in REGISTERS:
        said = [speak_date(first + timedelta(days=n), register) for n in range(31)]
        assert len(set(said)) == 31, register
        assert not any(re.search(r"\d", s) for s in said), register
    assert speak_date(date(2026, 12, 21), "msa") == "الاثنين الحادي والعشرين من ديسمبر"
    assert speak_date(date(2026, 12, 20), "msa") == "الأحد العشرين من ديسمبر"
    assert speak_date(date(2026, 12, 31), "en") == "Thursday the thirty-first of December"
    assert speak_date(date(2026, 12, 13), "en") == "Sunday the thirteenth of December"
