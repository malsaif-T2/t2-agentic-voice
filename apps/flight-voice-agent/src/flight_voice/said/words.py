"""The flight agent's fixed words with no number in them, in Saudi Arabic, MSA and English: the
weekdays and months, the cabins, the parts of the day, a route ("Riyadh to London", «من الرياض
للندن»), a trip's kind and the fare's basis ("per person, one way").

The parts of the day are two things. A caller's pick of "the morning one" is one of four parts,
the same in every language (`part_of_day`): morning 05:00 to 11:59, afternoon 12:00 to 17:59,
evening 18:00 to 21:59, night 22:00 to 04:59. What a reply says of a time is finer in Saudi
Arabic (`part_said`): «الفجر» to 04:59, «الصبح» to 11:59, «الظهر» to 14:59, «العصر» to 17:59,
«المغرب» to 18:59, «بالليل» to 23:59. Arabic is written plainly, as Ole5's data modules do.
"""

from __future__ import annotations

from datetime import date, time
from typing import Final, Literal

from flight_voice.airline.airports import AIRPORTS, Code, Register
from flight_voice.airline.schedule import Cabin

PartOfDay = Literal["morning", "afternoon", "evening", "night"]

# By Python's weekday, Monday first.
_WEEKDAYS_EN: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_WEEKDAYS_AR: Final = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_MONTHS_EN: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTHS_AR: Final = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)
_CABINS_EN: Final[dict[Cabin, str]] = {
    "economy": "economy",
    "business": "business class",
    "first": "first class",
}
_CABINS_AR: Final[dict[Cabin, str]] = {
    "economy": "الدرجة السياحية",
    "business": "درجة رجال الأعمال",
    "first": "الدرجة الأولى",
}
# Each register's parts of the day: the hour each begins at, and its words, in day order.
_PARTS: Final[dict[Register, tuple[tuple[int, str], ...]]] = {
    "saudi": (
        (0, "الفجر"),
        (5, "الصبح"),
        (12, "الظهر"),
        (15, "العصر"),
        (18, "المغرب"),
        (19, "بالليل"),
    ),
    "msa": ((0, "فجرًا"), (5, "صباحًا"), (12, "ظهرًا"), (15, "عصرًا"), (18, "مساءً")),
    "en": (
        (0, "at night"),
        (5, "in the morning"),
        (12, "in the afternoon"),
        (18, "in the evening"),
        (22, "at night"),
    ),
}
_PICKS: Final[tuple[tuple[int, PartOfDay], ...]] = (
    (0, "night"),
    (5, "morning"),
    (12, "afternoon"),
    (18, "evening"),
    (22, "night"),
)
FARE_BASIS: Final[dict[Register, str]] = {
    "saudi": "للشخص، رايح بس",
    "msa": "للشخص، ذهاب فقط",
    "en": "per person, one way",
}
_TRIP_KINDS: Final[dict[Register, tuple[str, str]]] = {  # (round trip, one way)
    "saudi": ("رايح جاي", "رايح بس"),
    "msa": ("ذهاب وعودة", "ذهاب فقط"),
    "en": ("round trip", "one way"),
}


def weekday(day: date, register: Register) -> str:
    """The day's weekday: "Thursday", «الخميس» (the same in both Arabic registers)."""
    names = _WEEKDAYS_EN if register == "en" else _WEEKDAYS_AR
    return names[day.weekday()]


def weekday_short(day: date) -> str:
    """The day's weekday as an English card writes it: "Thu"."""
    return _WEEKDAYS_EN[day.weekday()][:3]


def month(number: int, register: Register) -> str:
    """The month `number` (1 to 12): "December", «ديسمبر» (the same in both Arabic registers)."""
    names = _MONTHS_EN if register == "en" else _MONTHS_AR
    return names[number - 1]


def month_short(number: int) -> str:
    """The month as an English card writes it: "Dec"."""
    return _MONTHS_EN[number - 1][:3]


def cabin(name: Cabin, register: Register) -> str:
    """The cabin's name: "business class", «درجة رجال الأعمال»."""
    return (_CABINS_EN if register == "en" else _CABINS_AR)[name]


def _of(at: time, parts: tuple[tuple[int, str], ...]) -> str:
    return [words for hour, words in parts if hour <= at.hour][-1]


def part_said(at: time, register: Register) -> str:
    """The part of the day `at` falls in, as a reply says it: «العصر», "in the afternoon"."""
    return _of(at, _PARTS[register])


def part_of_day(at: time) -> PartOfDay:
    """The part of the day `at` falls in, as a caller picks a flight by it."""
    part: PartOfDay = next(p for hour, p in reversed(_PICKS) if hour <= at.hour)
    return part


def route(origin: Code, destination: Code, register: Register) -> str:
    """A route: "Riyadh to London", «من الرياض للندن» in Saudi, «من الرياض إلى لندن» in MSA."""
    start, end = AIRPORTS[origin], AIRPORTS[destination]
    if register == "en":
        return f"{start.city_en} {end.to_city('en')}"
    return f"{start.from_city(register)} {end.to_city(register)}"


def trip_kind(one_way: bool, register: Register) -> str:
    """A trip's kind: "round trip" or "one way", «رايح جاي» or «رايح بس»."""
    return _TRIP_KINDS[register][1 if one_way else 0]
