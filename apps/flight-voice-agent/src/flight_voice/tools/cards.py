"""The card each flight result shows on the page, in the reply's script: an extra that mirrors
what the reply says, never needed (D-075). Each option is one step string.

A card's text is the airline's fixed data and values the code computed, never the caller's
words, and every number on it is in its result's data, so the output guard's ID rule passes it.
The rule reads numbers standing next to each other with only marks between them as one group, so
a word always sits between two numbers ("flight T2 401 on a 787-9 for 2,450 SAR"), and times
are joined by "to" / «إلى». Arabic cards write times, lengths and fares in Arabic-Indic digits;
a flight's name and its aircraft keep their Latin letters and digits.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from t2_agentic_voice import Card

from flight_voice.airline.airports import AIRPORTS, Code
from flight_voice.said import Tag, arabic, register, words
from flight_voice.tools.results import Duration, Listing, Option

_INDIC: Final = str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩٬")
LOWEST_EN: Final = "lowest fare"
LOWEST_AR: Final = "أقل سعر"
FULL_EN: Final = "full in this cabin"
FULL_AR: Final = "ممتلئة في هذه الدرجة"


def indic(text: str) -> str:
    """`text` with its Western digits and thousands commas written as Arabic-Indic ones."""
    return text.translate(_INDIC)


def money(amount: int, tag: Tag) -> str:
    """An amount in riyals as a card writes it: "2,450 SAR", «٢٬٤٥٠ ريال»."""
    grouped = f"{amount:,}"
    return f"{indic(grouped)} ريال" if arabic(tag) else f"{grouped} SAR"


def length(duration: Duration, tag: Tag) -> str:
    """A flight's length as a card writes it: "7 h 5 min", or in Arabic the
    hours and «س», the minutes and «د», in Arabic-Indic digits."""
    if arabic(tag):
        made = f"{duration.hours} س" + (f" {duration.minutes} د" if duration.minutes else "")
        return indic(made)
    return f"{duration.hours} h" + (f" {duration.minutes} min" if duration.minutes else "")


def day_title(day: date, tag: Tag) -> str:
    """A day as a card's title writes it: "Thu 17 Dec", or in Arabic
    «الخميس», the day in Arabic-Indic digits, «ديسمبر»."""
    if arabic(tag):
        r = register(tag)
        return f"{words.weekday(day, r)} {indic(str(day.day))} {words.month(day.month, r)}"
    return f"{words.weekday_short(day)} {day.day} {words.month_short(day.month)}"


def route_title(origin: Code, destination: Code, tag: Tag) -> str:
    """A route as a card's title writes it: "Riyadh to London", «الرياض إلى لندن»."""
    start, end = AIRPORTS[origin], AIRPORTS[destination]
    if arabic(tag):
        return f"{start.city_ar} إلى {end.city_ar}"
    return f"{start.city_en} to {end.city_en}"


def option_step(option: Option, tag: Tag) -> str:
    """One option as a card's step: its times, length, flight, aircraft and fare, and its mark."""
    if arabic(tag):
        times = indic(f"{option.departs} إلى {option.arrives}")
        times += " من اليوم التالي" if option.next_day else ""
        step = (
            f"{times}، {length(option.duration, tag)}، مباشرة، رحلة {option.flight} على "
            f"{option.aircraft} بسعر {money(option.fare_sar, tag)}"
        )
        mark = LOWEST_AR if option.mark else (FULL_AR if not option.seats_ok else "")
        return f"{step}، {mark}" if mark else step
    times = f"{option.departs} to {option.arrives}" + (" next day" if option.next_day else "")
    article = "an" if option.aircraft.startswith("A") else "a"
    step = (
        f"{times}, {length(option.duration, tag)}, nonstop, flight {option.flight} on {article} "
        f"{option.aircraft} for {money(option.fare_sar, tag)}"
    )
    mark = LOWEST_EN if option.mark else (FULL_EN if not option.seats_ok else "")
    return f"{step}, {mark}" if mark else step


def listing_card(listing: Listing, origin: Code, destination: Code, day: date, tag: Tag) -> Card:
    """A leg's options on `day`: the route and the day, then one step per option."""
    title = route_title(origin, destination, tag)
    sep = "، " if arabic(tag) else ", "
    return Card(
        title=f"{title}{sep}{day_title(day, tag)}",
        steps=tuple(option_step(o, tag) for o in listing.options),
    )
