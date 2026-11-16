"""The card each flight result shows on the page, in the reply's script: an extra that mirrors
what the reply says, never needed (D-075). Each option is one of the card's rows (`CardRow`): a
listed flight's times as its title, its length, stops, flight and aircraft as its detail, its fare
as its value, and its mark (`best` on the cheapest, `chosen` on a leg picked, `unavailable` on one
full in the cabin), which the page maps to a style; a listing holds at most four.

A card's text is the airline's fixed data and values the code computed, never the caller's
words, and every number on it is in its result's data, so the output guard's ID rule passes it.
The rule reads numbers standing next to each other with only marks between them as one group, so
a word always sits between two numbers ("flight T2 401 on a 787-9 for 2,450 SAR"), and times
are joined by "to" / «إلى». Arabic cards write times, lengths and fares in Arabic-Indic digits;
a flight's name and its aircraft keep their Latin letters and digits.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Final

from t2_agentic_voice import Card, CardRow

from flight_voice.airline.airports import AIRPORTS, Code
from flight_voice.airline.schedule import Cabin
from flight_voice.said import Tag, arabic, register, words
from flight_voice.tools.results import Duration, Listing, Option
from flight_voice.trip import TripDraft

if TYPE_CHECKING:
    from flight_voice.tools.trip_view import TripView

_INDIC: Final = str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩٬")


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


def times(option: Option, tag: Tag) -> str:
    """A flight's local times at each end, joined by a word: "09:10 to 16:15", with "next day"
    when it lands the day after."""
    if arabic(tag):
        joined = indic(f"{option.departs} إلى {option.arrives}")
        return joined + (" من اليوم التالي" if option.next_day else "")
    return f"{option.departs} to {option.arrives}" + (" next day" if option.next_day else "")


def flown(option: Option, tag: Tag) -> str:
    """A flight's length, stops, name and aircraft: "7 h 5 min, nonstop, flight T2 401 on a
    787-9"."""
    if arabic(tag):
        return f"{length(option.duration, tag)}، مباشرة، رحلة {option.flight} على {option.aircraft}"
    article = "an" if option.aircraft.startswith("A") else "a"
    return f"{length(option.duration, tag)}, nonstop, flight {option.flight} on {article} " + (
        option.aircraft
    )


def option_row(
    option: Option, tag: Tag, *, title: str | None = None, chosen: bool = False
) -> CardRow:
    """One option as a card's row: its times (or `title`, with the times moved to the detail),
    its flight, its fare, and its mark: `unavailable` when it has no seat for every traveler,
    else `chosen` when picked, else `best` on the cheapest."""
    sep = "، " if arabic(tag) else ", "
    detail = (
        flown(option, tag) if title is None else f"{times(option, tag)}{sep}{flown(option, tag)}"
    )
    return CardRow(
        title=times(option, tag) if title is None else title,
        detail=detail,
        value=money(option.fare_sar, tag),
        mark="unavailable"
        if not option.seats_ok
        else ("chosen" if chosen else ("best" if option.mark else None)),
    )


def listing_card(listing: Listing, origin: Code, destination: Code, day: date, tag: Tag) -> Card:
    """A leg's options on `day`: the route and the day, then one row per option."""
    title = route_title(origin, destination, tag)
    sep = "، " if arabic(tag) else ", "
    return Card(
        title=f"{title}{sep}{day_title(day, tag)}",
        rows=tuple(option_row(o, tag) for o in listing.options),
    )


TRIP_EN: Final = "Your trip"
TRIP_AR: Final = "رحلتك"


def party(travelers: int, cabin: Cabin, tag: Tag) -> str:
    """The travelers and the cabin as a card writes them: "2 travelers in business class",
    «مسافران في درجة رجال الأعمال»."""
    if arabic(tag):
        counted = {1: "مسافر واحد", 2: "مسافران"}.get(travelers, f"{indic(str(travelers))} مسافرين")
        return f"{counted} في {words.cabin(cabin, register(tag))}"
    noun = "traveler" if travelers == 1 else "travelers"
    return f"{travelers} {noun} in {words.cabin(cabin, 'en')}"


def trip_card(trip: TripView, draft: TripDraft, tag: Tag) -> Card | None:
    """The trip planned so far: a row for each chosen leg (its route and day, its flight, its
    fare, marked chosen), then the travelers and the cabin, then the total once every leg is
    chosen; none while nothing is planned."""
    if draft.destination is None:
        return None
    rows: list[CardRow] = []
    legs = (
        (trip.outbound, draft.chosen_outbound, False),
        (trip.return_flight, draft.chosen_return, True),
    )
    sep = "، " if arabic(tag) else ", "
    for option, chosen, back in legs:
        if option is None or chosen is None:
            continue
        start, end = (
            (draft.destination, draft.origin) if back else (draft.origin, draft.destination)
        )
        where = f"{route_title(start, end, tag)}{sep}{day_title(chosen.day, tag)}"
        rows.append(option_row(option, tag, title=where, chosen=True))
    rows.append(CardRow(title=party(trip.travelers, trip.cabin, tag)))
    if trip.total_sar is not None:
        total = "المجموع" if arabic(tag) else "Total"
        rows.append(CardRow(title=total, value=money(trip.total_sar, tag)))
    return Card(title=TRIP_AR if arabic(tag) else TRIP_EN, rows=tuple(rows))
