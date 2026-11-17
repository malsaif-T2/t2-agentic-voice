"""A search over a span of days (status `days`): what flies on a route over the days the caller
asked about when they named no single day ("next week", «هالويكند», the soonest).

The span is resolved in code inside the booking window (airline/dates.py's `resolve_span`), and
the answer comes before the round-trip gate: no return day is asked for first, and nothing is
written to the call's draft, so no day the caller did not choose is kept. The result holds the
span's first and last days, the route's daily departure times, the days with no flight, each
day that has one with its lowest fare in the cabin (the fare calendar's), and the two cheapest
of them marked; its `say` asks for the span, the times, the two cheapest days and which day
they would like to leave. Its card is a calendar of flights: one row a day, the cheapest
marked. A span wholly past the window is a date problem, a cabin the route does not sell is
`cabin_not_offered`, and a span with no flight at all is `no_flights_that_day`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final, Literal

from t2_agentic_voice import Card, CardRow, ToolError, ToolResult

from flight_voice.airline.airports import Airport, Code
from flight_voice.airline.dates import DateProblem, Days, resolve_span
from flight_voice.airline.fares import FareDay
from flight_voice.airline.schedule import CABINS, Cabin, flights
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag, arabic, words
from flight_voice.tools.cards import day_title, leg_title, money
from flight_voice.tools.results import (
    SAY,
    SEARCH_FAILED,
    CabinNotOffered,
    DateIssue,
    DateSaid,
    NoFlights,
    _Result,
    date_said,
    result,
    said,
)

# How many of the span's cheapest days are marked to be said.
MARKED: Final = 2


class OverviewDay(_Result):
    """A day of the span that has a flight: its date, its lowest fare, and the mark on the two
    cheapest."""

    date: DateSaid
    fare_sar: int
    mark: Literal["cheapest"] | None = None


class Overview(_Result):
    """What flies over a span of days (the module's docstring)."""

    status: Literal["days"] = "days"
    route_said: str
    route_said_msa: str | None = None
    first: DateSaid
    last: DateSaid
    departs: tuple[str, ...]
    no_flight_days: tuple[DateSaid, ...] | None = None
    days: tuple[OverviewDay, ...]
    cabin: Cabin
    cabin_said: str
    cabin_said_msa: str | None = None
    fare_basis_said: str
    fare_basis_said_msa: str | None = None
    say: str


def marked(found: tuple[FareDay, ...], tag: Tag) -> tuple[OverviewDay, ...]:
    """Each day of `found` with a fare, in date order, the `MARKED` cheapest marked; of two
    days as cheap, the earlier."""
    priced = [d for d in found if d.fare is not None]
    cheapest = {d.day for d in sorted(priced, key=lambda d: (d.fare, d.day))[:MARKED]}
    return tuple(
        OverviewDay(
            date=date_said(d.day, tag),
            fare_sar=d.fare or 0,
            mark="cheapest" if d.day in cheapest else None,
        )
        for d in priced
    )


async def span_search(
    airline: Airline,
    route: tuple[Airport, Airport],
    spec: Days,
    cabin: Cabin,
    tag: Tag,
    nearest: Callable[[date], list[date]],
) -> ToolResult:
    """The answer to a search whose departure is the span `spec`, on `route` in `cabin`
    (the module's docstring); `nearest` gives the days nearest a day that have a flight."""
    start, end = route
    span = resolve_span(spec, airline.today())
    if isinstance(span, DateProblem):
        issue = DateIssue(
            leg="outbound",
            problem=span.problem,
            last_day=date_said(span.last_day, tag),
            say=SAY[span.problem],
        )
        return result(issue)
    sold = flights(start.code, end.code)
    if cabin not in sold[0].cabins:
        offered = tuple(c for c in CABINS if c in sold[0].cabins)
        return result(CabinNotOffered(cabin=cabin, offered=offered))
    first, last = span
    try:
        found = await airline.calendar(start.code, end.code, first, last, cabin)
    except AirlineUnavailableError:
        raise ToolError(SEARCH_FAILED) from None
    days = marked(found, tag)
    if not days:
        near = tuple(date_said(d, tag) for d in nearest(first))
        return result(NoFlights(leg="outbound", date=date_said(first, tag), nearest=near))
    empty = tuple(date_said(d.day, tag) for d in found if d.fare is None)
    route_said, route_msa = said(lambda r: words.route(start.code, end.code, r), tag)
    cabin_said, cabin_msa = said(lambda r: words.cabin(cabin, r), tag)
    basis, basis_msa = said(words.FARE_BASIS.__getitem__, tag)
    answer = Overview(
        route_said=route_said,
        route_said_msa=route_msa,
        first=date_said(first, tag),
        last=date_said(last, tag),
        departs=tuple(f.departs.strftime("%H:%M") for f in sold),
        no_flight_days=empty or None,
        days=days,
        cabin=cabin,
        cabin_said=cabin_said,
        cabin_said_msa=cabin_msa,
        fare_basis_said=basis,
        fare_basis_said_msa=basis_msa,
        say=SAY["days_some" if empty else "days"],
    )
    return result(answer, overview_card(answer, found, (start.code, end.code), tag))


def overview_card(
    answer: Overview, found: tuple[FareDay, ...], route: tuple[Code, Code], tag: Tag
) -> Card:
    """The calendar of flights, in the outbound segment (`slot`): the leg, the route, the span
    and the cabin, then a row for each day, its lowest fare as its value, the two cheapest
    marked `best`, a day with no flight `unavailable`."""
    first, last = (day_title(date.fromisoformat(d.iso), tag) for d in (answer.first, answer.last))
    days = f"{first} إلى {last}" if arabic(tag) else f"{first} to {last}"
    cheapest = {d.date.iso for d in answer.days if d.mark}
    none = "لا رحلات" if arabic(tag) else "No flight"
    rows = tuple(
        CardRow(title=day_title(d.day, tag), detail=none, mark="unavailable")
        if d.fare is None
        else CardRow(
            title=day_title(d.day, tag),
            value=money(d.fare, tag),
            mark="best" if d.day.isoformat() in cheapest else None,
        )
        for d in found
    )
    title = leg_title("outbound", route, days, answer.cabin, tag)
    return Card(title=title, rows=rows, slot="outbound")
