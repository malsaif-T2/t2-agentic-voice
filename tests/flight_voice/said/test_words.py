"""The flight agent's fixed words with no number in them: weekdays and months in both scripts,
cabins, the parts of the day a reply says (finer in Saudi Arabic) and the four a caller picks
by, routes in each register, a trip's kind, the fare's basis, and which register a reply's
language is given."""

from __future__ import annotations

from datetime import date, time

import pytest
from flight_voice.airline.airports import REGISTERS
from flight_voice.airline.schedule import CABINS
from flight_voice.said import arabic, msa_too, register, words


def test_a_reply_is_given_its_registers_saudi_with_msa_beside_it() -> None:
    assert [register(t) for t in ("ar-SA", "ar", "en")] == ["saudi", "msa", "en"]
    assert [msa_too(t) for t in ("ar-SA", "ar", "en")] == [True, False, False]
    assert [arabic(t) for t in ("ar-SA", "ar", "en")] == [True, True, False]


def test_weekdays_and_months_in_both_scripts() -> None:
    thursday = date(2026, 12, 17)
    assert [words.weekday(thursday, r) for r in REGISTERS] == ["الخميس", "الخميس", "Thursday"]
    assert words.weekday_short(thursday) == "Thu"
    assert [words.month(12, r) for r in REGISTERS] == ["ديسمبر", "ديسمبر", "December"]
    assert words.month_short(1) == "Jan" and words.month(1, "saudi") == "يناير"
    week = [words.weekday(date(2026, 11, 15 + n), "en") for n in range(7)]
    assert week == ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    assert len({words.month(m, "msa") for m in range(1, 13)}) == 12


def test_every_cabin_has_its_name_in_each_register() -> None:
    assert [words.cabin(c, "en") for c in CABINS] == ["economy", "business class", "first class"]
    assert [words.cabin(c, "saudi") for c in CABINS] == [
        "الدرجة السياحية",
        "درجة رجال الأعمال",
        "الدرجة الأولى",
    ]


@pytest.mark.parametrize(
    ("at", "saudi", "msa", "english", "pick"),
    [
        ("02:10", "الفجر", "فجرًا", "at night", "night"),
        ("04:59", "الفجر", "فجرًا", "at night", "night"),
        ("05:00", "الصبح", "صباحًا", "in the morning", "morning"),
        ("09:10", "الصبح", "صباحًا", "in the morning", "morning"),
        ("12:00", "الظهر", "ظهرًا", "in the afternoon", "afternoon"),
        ("15:00", "العصر", "عصرًا", "in the afternoon", "afternoon"),
        ("18:15", "المغرب", "مساءً", "in the evening", "evening"),
        ("21:30", "بالليل", "مساءً", "in the evening", "evening"),
        ("22:05", "بالليل", "مساءً", "at night", "night"),
    ],
)
def test_the_part_of_the_day_said_and_picked(
    at: str, saudi: str, msa: str, english: str, pick: str
) -> None:
    moment = time.fromisoformat(at)
    said = [words.part_said(moment, r) for r in ("saudi", "msa", "en")]
    assert said == [saudi, msa, english]
    assert words.part_of_day(moment) == pick


def test_a_route_in_each_register_takes_the_saudi_lam() -> None:
    assert words.route("RUH", "LHR", "en") == "Riyadh to London"
    assert words.route("RUH", "LHR", "saudi") == "من الرياض للندن"
    assert words.route("RUH", "LHR", "msa") == "من الرياض إلى لندن"
    assert words.route("LHR", "RUH", "saudi") == "من لندن للرياض"
    assert words.route("RUH", "DOH", "saudi") == "من الرياض للدوحة"


def test_a_trip_kind_and_the_fare_basis_in_each_register() -> None:
    assert [words.trip_kind(False, r) for r in REGISTERS] == [
        "رايح جاي",
        "ذهاب وعودة",
        "round trip",
    ]
    assert [words.trip_kind(True, r) for r in REGISTERS] == ["رايح بس", "ذهاب فقط", "one way"]
    assert words.FARE_BASIS == {
        "saudi": "للشخص، رايح بس",
        "msa": "للشخص، ذهاب فقط",
        "en": "per person, one way",
    }
