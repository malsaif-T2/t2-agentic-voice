"""`find_flights` over a span of days (find.py): what flies on a route over the days the caller
asked about without naming one, at most `MOST_DAYS` of them, kept inside the booking window.

The result (`Spanned`, status `days`) holds the span's first and last days, each day that has a
flight with its weekday, its flight count in the cabin and its lowest fare (the airline's fare
calendar, read as its search mode says), the route's daily departure times, the days with no
flight and the two cheapest days, the earlier first of two as cheap. Nothing is written to the
call's trip, so no day the caller did not choose is kept. Its card is a calendar of days in the
outbound segment: a row a day, the two cheapest marked; past a card's most rows, the cheapest
days alone, in date order. A span with no flight at all is `no_flights`, with the nearest days
that have one.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final, Literal

from pydantic import JsonValue
from t2_agentic_voice import Card, CardRow, ToolResult

from flight_voice.airline.airports import Airport, Code
from flight_voice.airline.schedule import Cabin, departures, flights, window
from flight_voice.airline.system import Airline
from flight_voice.lean.results import FARES_ARE, Day, _Data, day_of, lean_result, route_said
from flight_voice.said import Tag, arabic
from flight_voice.tools import cards
from flight_voice.tools.search import nearest_days

MOST_DAYS: Final = 14
# The most rows a card holds (the library's `MAX_ROWS`).
CARD_ROWS: Final = 8
CHEAPEST: Final = 2


class DaySpan(_Data):
    """A span of days: its first and last days, at most `MOST_DAYS` days."""

    first: date
    last: date


class SpanDay(_Data):
    """A day of a span that has a flight: its weekday, its flights and its lowest fare."""

    date: str
    weekday: str
    flights: int
    lowest_fare: int


class Spanned(_Data):
    """What flies over a span of days (the module's docstring)."""

    status: Literal["days"] = "days"
    route: str
    route_msa: str | None = None
    first: Day
    last: Day
    cabin: Cabin
    fares_are: str = FARES_ARE
    departs: tuple[str, ...]
    days: tuple[SpanDay, ...]
    no_flight_days: tuple[Day, ...] = ()
    cheapest_days: tuple[str, ...]


async def span_search(
    airline: Airline, route: tuple[Airport, Airport], span: DaySpan, cabin: Cabin, tag: Tag
) -> ToolResult:
    """What flies over `span` on `route` in `cabin` (the module's docstring); a read that does
    not answer raises the airline's `AirlineUnavailableError`, which the tool says."""
    start, end = route
    today = airline.today()
    first, last = max(span.first, today), min(span.last, window(today)[1])
    found = await airline.calendar(start.code, end.code, first, last, cabin)
    days: list[SpanDay] = []
    empty: list[Day] = []
    for each in found:
        if each.fare is None:
            empty.append(day_of(each.day, tag))
            continue
        flown = departures(start.code, end.code, each.day)
        counted = sum(cabin in d.flight.cabins for d in flown)
        weekday = day_of(each.day, tag).weekday
        days.append(
            SpanDay(
                date=each.day.isoformat(), weekday=weekday, flights=counted, lowest_fare=each.fare
            )
        )
    if not days:
        near: list[JsonValue] = [
            day_of(n, tag).model_dump() for n in nearest_days(start, end, first, today)
        ]
        return lean_result({"status": "no_flights", "day": first.isoformat(), "nearest": near})
    cheapest = sorted(days, key=lambda d: (d.lowest_fare, d.date))[:CHEAPEST]
    said, msa = route_said((start.code, end.code), tag)
    answer = Spanned(
        route=said,
        route_msa=msa,
        first=day_of(first, tag),
        last=day_of(last, tag),
        cabin=cabin,
        departs=tuple(f.departs.strftime("%H:%M") for f in flights(start.code, end.code)),
        days=tuple(days),
        no_flight_days=tuple(empty),
        cheapest_days=tuple(d.date for d in cheapest),
    )
    return lean_result(answer, calendar_card(answer, (start.code, end.code), tag))


def calendar_card(answer: Spanned, route: tuple[Code, Code], tag: Tag) -> Card:
    """The span's calendar in the outbound segment (the module's docstring): a day with no
    flight `unavailable`, the two cheapest `best`, each day's lowest fare as its value."""
    first, last = (date.fromisoformat(d.date) for d in (answer.first, answer.last))
    ends = [cards.day_title(d, tag) for d in (first, last)]
    joined = " إلى ".join(ends) if arabic(tag) else " to ".join(ends)
    priced = {d.date: d for d in answer.days}
    every = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    if len(every) > CARD_ROWS:
        kept = sorted(answer.days, key=lambda d: (d.lowest_fare, d.date))[:CARD_ROWS]
        every = sorted(date.fromisoformat(d.date) for d in kept)
    none = "لا رحلات" if arabic(tag) else "No flight"
    rows = []
    for day in every:
        each = priced.get(day.isoformat())
        title = cards.day_title(day, tag)
        if each is None:
            rows.append(CardRow(title=title, detail=none, mark="unavailable"))
            continue
        best: Literal["best"] | None = "best" if each.date in answer.cheapest_days else None
        rows.append(CardRow(title=title, value=cards.money(each.lowest_fare, tag), mark=best))
    title = cards.leg_title("outbound", route, joined, answer.cabin, tag)
    return Card(title=title, rows=tuple(rows), slot="outbound")
