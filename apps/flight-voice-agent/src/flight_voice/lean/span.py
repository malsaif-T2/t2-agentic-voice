"""`find_flights` over a span of days (find.py): what flies on a route over the days the caller
asked about without naming one, at most `MOST_DAYS` of them (two months, the owner's ruling of
2026-11-17), kept between today and the source's last day.

The source answers the lowest price of each day for all the travelers (`days`); a route the
mock does not fly and a cabin it does not sell are refused before any day is read. The result
(`Spanned`, status `days`) holds the span's first and last days, the route's daily departure
times when the source has fixed ones (the mock), the two cheapest days with their prices
(`cheapest`, the earlier first of two as cheap; `cheapest_days` their dates), the days that
could not be checked (`unknown_days`), and, when the source cut the span to its own most days,
the last day it checked (`checked_last`) with a note. Then, by the span's length:

- **Up to `DAILY_DAYS` days:** each day that has a flight with its weekday, its flight count in
  the cabin (left out when the source counted none: SerpApi's fare calendar prices each day but
  never says 0 for a count it does not know) and its lowest price (`days`), and the days with
  no flight.
- **Longer:** week by week (`weeks`, the Saudi week Sunday to Saturday, cut to the span): each
  week's first and last days, how many of its days have a flight, and its cheapest day with its
  price; no list of single days, so the result stays short however long the span.

**Each day's flights** (`flights_per_day`, plan 011's round 2: asked for the priciest flight of
a span, the model had only each day's lowest price): when the caller asks beyond each day's
cheapest price, every day is searched (the span cut to `DAILY_DAYS` and to the source's own
`span_days`, `checked_last` then set; on the real network each day cached, under the span's
concurrency and deadline), and each day that has a flight also gives, over the flights a day's
search lists from (listing.py's pool), its highest price, its first and last departures and the
airlines flying it, with a note that a day's flights come from find_flights for that day, at
once (`TO_PICK`).

Nothing is written to the call's trip, so no day the caller did not choose is kept. Its card is
a calendar of days in the outbound segment: a row a day, the two cheapest marked; past a card's
most rows, the cheapest days alone, in date order. A span with no flight at all is `no_flights`,
with the nearest days that have one. A source that answered no day raises, and the tool says
the search failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal

from pydantic import JsonValue
from t2_agentic_voice import Card, CardRow, ToolResult

from flight_voice.flight_data.model import Cabin, Place
from flight_voice.flight_data.port import FlightData
from flight_voice.flight_data.queries import SpanQuery
from flight_voice.lean.offer_cards import leg_title
from flight_voice.lean.results import (
    Day,
    Network,
    _Data,
    day_of,
    fares_are,
    lean_result,
    route_said,
)
from flight_voice.lean.span_days import SpanDay, read_days
from flight_voice.said import Tag, arabic
from flight_voice.tools import cards

MOST_DAYS: Final = 62
# The longest span still given day by day; a longer one is given week by week.
DAILY_DAYS: Final = 14
# The most rows a card holds (the library's `MAX_ROWS`).
CARD_ROWS: Final = 8
CHEAPEST: Final = 2
TO_BOOK: Final = (
    "To book, call find_flights with one of these days as depart, then choose its flight."
)
TO_HEAR: Final = (
    "To hear a day's flights, call find_flights with one of these days as depart, then choose "
    "its flight."
)
CHECKED_LAST: Final = "Only the days up to checked_last were checked; offer the days after."
TO_PICK: Final = (
    "To choose a flight, call find_flights with its day as depart: an instant answer, since "
    "each day was just searched."
)


class DaySpan(_Data):
    """A span of days: its first and last days, at most `MOST_DAYS` days."""

    first: date
    last: date


class SpanWeek(_Data):
    """A week of a long span (Sunday to Saturday, cut to the span): how many of its days have a
    flight, and its cheapest day."""

    first: Day
    last: Day
    days_with_flights: int
    cheapest: SpanDay


class Spanned(_Data):
    """What flies over a span of days (the module's docstring)."""

    status: Literal["days"] = "days"
    route: str
    route_msa: str | None = None
    first: Day
    last: Day
    cabin: Cabin
    travelers: int
    fares_are: str
    fares_are_msa: str | None = None
    departs: tuple[str, ...] | None = None
    days: tuple[SpanDay, ...] = ()
    weeks: tuple[SpanWeek, ...] = ()
    no_flight_days: tuple[Day, ...] = ()
    unknown_days: tuple[Day, ...] | None = None
    checked_last: str | None = None
    cheapest: tuple[SpanDay, ...]
    cheapest_days: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class SpanAsked:
    """A span search as asked: the source, the route, the cabin and travelers, the day it is,
    the network, the reply's tag, and whether each day's flights are asked (`each_day`)."""

    data: FlightData
    route: tuple[Place, Place]
    cabin: Cabin
    travelers: int
    today: date
    network: Network
    tag: Tag
    each_day: bool = False


async def span_search(asked: SpanAsked, span: DaySpan) -> ToolResult | dict[str, JsonValue]:
    """What flies over `span` (the module's docstring); a refusal of the route (`not_served`)
    or the cabin (`cabin_not_offered`) as data, for find.py to say; a source that answered no
    day raises its `FlightDataUnavailableError`, which the tool says."""
    start, end = asked.route
    tag, today = asked.tag, asked.today
    first = max(span.first, today)
    last = max(first, min(span.last, asked.data.last_day(today)))
    cut = first + timedelta(days=DAILY_DAYS - 1)
    cut_at = cut if asked.each_day and last > cut else None
    q = SpanQuery(
        origin=start,
        destination=end,
        first=first,
        last=last if cut_at is None else cut_at,
        cabin=asked.cabin,
        adults=asked.travelers,
        each_day=asked.each_day,
    )
    last = q.last
    found = await asked.data.days(q)
    if found.status == "not_served":
        return {"status": "not_served"}
    if found.status == "cabin_not_sold":
        offered: list[JsonValue] = list(found.cabins or ())
        return {"status": "cabin_not_offered", "cabin": asked.cabin, "offered": offered}
    days, empty, unknown = read_days(found, tag, asked.each_day)
    if not days and not unknown:
        nearest = await asked.data.nearest(q.day(first), today)
        near: list[JsonValue] = [day_of(n, tag).model_dump() for n in nearest]
        return lean_result({"status": "no_flights", "day": first.isoformat(), "nearest": near})
    cheapest = sorted(days, key=lambda d: (d.lowest_price, d.date))[:CHEAPEST]
    said, msa = route_said((start, end), tag)
    daily = (last - first).days < DAILY_DAYS
    basis, basis_msa = fares_are(
        tag, round_trip=False, travelers=asked.travelers, network=asked.network
    )
    note = TO_PICK if asked.each_day else (TO_BOOK if asked.network == "mock" else TO_HEAR)
    checked_last = found.checked_last or cut_at
    answer = Spanned(
        route=said,
        route_msa=msa,
        fares_are=basis,
        fares_are_msa=basis_msa,
        first=day_of(first, tag),
        last=day_of(last, tag),
        cabin=asked.cabin,
        travelers=asked.travelers,
        departs=found.times,
        days=tuple(days) if daily else (),
        weeks=() if daily else by_week(days, tag),
        no_flight_days=tuple(empty) if daily else (),
        unknown_days=tuple(unknown) or None,
        checked_last=None if checked_last is None else checked_last.isoformat(),
        cheapest=tuple(cheapest),
        cheapest_days=tuple(d.date for d in cheapest),
        note=note if checked_last is None else f"{note} {CHECKED_LAST}",
    )
    shown = (
        days
        if daily
        else sorted(
            {d.date: d for d in (*(w.cheapest for w in answer.weeks), *cheapest)}.values(),
            key=lambda d: d.date,
        )
    )
    return lean_result(answer, calendar_card(answer, shown, (start, end), tag))


def by_week(days: list[SpanDay], tag: Tag) -> tuple[SpanWeek, ...]:
    """`days` (each with a flight, in date order) grouped by the Saudi week, Sunday to Saturday:
    a week with no flight is left out (the module's docstring)."""
    weeks: dict[date, list[SpanDay]] = {}
    for each in days:
        day = date.fromisoformat(each.date)
        sunday = day - timedelta(days=(day.weekday() + 1) % 7)
        weeks.setdefault(sunday, []).append(each)
    return tuple(
        SpanWeek(
            first=day_of(date.fromisoformat(held[0].date), tag),
            last=day_of(date.fromisoformat(held[-1].date), tag),
            days_with_flights=len(held),
            cheapest=min(held, key=lambda d: (d.lowest_price, d.date)),
        )
        for held in weeks.values()
    )


def calendar_card(
    answer: Spanned, days: list[SpanDay], route: tuple[Place, Place], tag: Tag
) -> Card:
    """The span's calendar in the outbound segment (the module's docstring): a day with no
    flight `unavailable`, the two cheapest `best`, each day's lowest price as its value. `days`
    are the days the result holds (a long span's: each week's cheapest and the two cheapest), so
    the card shows no day or price the result does not; a day not checked is left out."""
    first, last = (date.fromisoformat(d.date) for d in (answer.first, answer.last))
    ends = [cards.day_title(d, tag) for d in (first, last)]
    joined = " إلى ".join(ends) if arabic(tag) else " to ".join(ends)
    priced = {d.date: d for d in days}
    unknown = {d.date for d in answer.unknown_days or ()}
    every = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    every = [d for d in every if d.isoformat() not in unknown]
    if len(every) > CARD_ROWS:
        kept = sorted(days, key=lambda d: (d.lowest_price, d.date))[:CARD_ROWS]
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
        rows.append(CardRow(title=title, value=cards.money(each.lowest_price, tag), mark=best))
    title = leg_title("outbound", route, joined, answer.cabin, tag)
    return Card(title=title, rows=tuple(rows), slot="outbound")
