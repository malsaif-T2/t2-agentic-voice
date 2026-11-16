"""`fare_calendar`: the cheapest days to fly a route, in a month or the 30 days from a date.

The talker passes the city as the caller said it, and a month (1 to 12) or a date form; with
neither, the span is the 30 days from today. The code picks the year: a month before this one is
next year's. The span keeps to the booking window, and a span wholly past it is a date problem.
The result holds the span's seven cheapest days in date order, each with its fare (so every
number the card shows is in the data), the three cheapest of them marked for speech, the span's
highest fare (so the talker can say "from ... to ... riyals"), and how many days have no flight;
a day with no flight is left out, never given a fare. A span with no flight at all is
`no_flights_that_day`, with the nearest days that have one. A calendar that does not answer is a
`ToolError` that says it failed, never "no flights".
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import CallContext, Card, Tool, ToolError, ToolResult, tool

from flight_voice.airline.airports import HOME, airport, find_airport
from flight_voice.airline.dates import DateProblem, DateSpec, resolve_departure
from flight_voice.airline.fares import FareDay
from flight_voice.airline.schedule import CABINS, Cabin, flights, route_served, window
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag, arabic, register, words
from flight_voice.tools.cards import day_title, money, route_title
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
from flight_voice.tools.search import nearest_days, not_served

FARE_CALENDAR: Final = "fare_calendar"
DESCRIPTION: Final = (
    "Find the cheapest days to fly a route, in a month or the 30 days from a date. Call it when "
    "the caller asks when it is cheapest, or is flexible on dates."
)
BOTH: Final = "Pass month or from_date, not both: the one the caller said."
_CITY: Final = "The city as the caller said it, in their words."
_ORIGIN: Final = "The city they leave from, only when it is not Riyadh."
_MONTH: Final = "The month the caller asked about, 1 to 12; the year is worked out for you."
_FROM: Final = "The first day of the 30 days, as a date form, when the caller gave a day."
_CABIN: Final = "The cabin, when the caller named one; else leave it out."
SPAN_DAYS: Final = 30
SHOWN: Final = 7
SAID: Final = 3
AMONG_EN: Final = "among the cheapest"
AMONG_AR: Final = "من الأرخص"


class CalendarDay(_Result):
    """A day of the calendar: its date, its cheapest fare, and the mark on the three said."""

    date: DateSaid
    fare_sar: int
    mark: Literal["cheapest"] | None = None


class Calendar(_Result):
    """The cheapest days of a span (the module's docstring)."""

    status: Literal["ok"] = "ok"
    route_said: str
    route_said_msa: str | None = None
    month_said: str | None = None
    first: DateSaid
    last: DateSaid
    cabin: Cabin
    cabin_said: str
    cabin_said_msa: str | None = None
    days: tuple[CalendarDay, ...]
    highest_sar: int
    no_flight_days: int | None = None
    fare_basis_said: str
    fare_basis_said_msa: str | None = None
    say: str = SAY["calendar"]


def month_span(month: int, today: date) -> tuple[date, date]:
    """The days of `month` from today on: this year's when it has not ended, else next year's."""
    year = today.year if month >= today.month else today.year + 1
    after = date(year + month // 12, month % 12 + 1, 1)
    return max(date(year, month, 1), today), after - timedelta(days=1)


def cheapest(days: tuple[FareDay, ...], tag: Tag) -> tuple[CalendarDay, ...]:
    """The `SHOWN` cheapest days with a fare, in date order, the `SAID` cheapest marked; of two
    days as cheap, the earlier comes first."""
    priced = sorted((d for d in days if d.fare is not None), key=lambda d: (d.fare, d.day))
    kept = priced[:SHOWN]
    marked = {d.day for d in kept[:SAID]}
    return tuple(
        CalendarDay(
            date=date_said(d.day, tag),
            fare_sar=d.fare or 0,
            mark="cheapest" if d.day in marked else None,
        )
        for d in sorted(kept, key=lambda d: d.day)
    )


def span(
    month: int | None, from_date: DateSpec | None, today: date
) -> tuple[date, date] | DateProblem:
    """The days the calendar covers, inside the booking window: the month's from today on, the
    30 from `from_date`, or the 30 from today; a date problem when none of them can be sold."""
    last_day = window(today)[1]
    if from_date is not None:
        resolved = resolve_departure(from_date, today)
        if isinstance(resolved, DateProblem):
            return resolved
        first, last = resolved.day, resolved.day + timedelta(days=SPAN_DAYS - 1)
    elif month is not None:
        first, last = month_span(month, today)
    else:
        first, last = today, today + timedelta(days=SPAN_DAYS - 1)
    if first > last_day:
        return DateProblem("beyond_window", last_day)
    return first, min(last, last_day)


def fare_calendar(airline: Airline) -> Tool:
    """The fare calendar over `airline` (the module's docstring)."""

    @tool(name=FARE_CALENDAR, description=DESCRIPTION, progress="fares")
    async def find(
        ctx: CallContext,
        destination: Annotated[str, Field(min_length=1, max_length=40, description=_CITY)],
        origin: Annotated[str | None, Field(max_length=40, description=_ORIGIN)] = None,
        month: Annotated[int | None, Field(ge=1, le=12, description=_MONTH)] = None,
        from_date: Annotated[DateSpec | None, Field(description=_FROM)] = None,
        cabin: Annotated[Cabin, Field(description=_CABIN)] = "economy",
    ) -> ToolResult:
        tag: Tag = ctx.language
        if month is not None and from_date is not None:
            raise ToolError(BOTH)
        today = airline.today()
        end = find_airport(destination)
        start = airport(HOME) if origin is None else find_airport(origin)
        if end is None or start is None:
            return not_served("not_served_city", tag)
        if not route_served(start.code, end.code):
            return not_served("not_served_route", tag)
        days_asked = span(month, from_date, today)
        if isinstance(days_asked, DateProblem):
            issue = DateIssue(
                leg="outbound",
                problem=days_asked.problem,
                last_day=date_said(days_asked.last_day, tag),
                say=SAY[days_asked.problem],
            )
            return result(issue)
        first, last = days_asked
        sold = flights(start.code, end.code)[0].cabins
        if cabin not in sold:
            return result(
                CabinNotOffered(cabin=cabin, offered=tuple(c for c in CABINS if c in sold))
            )
        try:
            found = await airline.calendar(start.code, end.code, first, last, cabin)
        except AirlineUnavailableError:
            raise ToolError(SEARCH_FAILED) from None
        days = cheapest(found, tag)
        if not days:
            near = nearest_days(start, end, first, today)
            return result(
                NoFlights(
                    leg="outbound",
                    date=date_said(first, tag),
                    nearest=tuple(date_said(d, tag) for d in near),
                )
            )
        route, route_msa = said(lambda r: words.route(start.code, end.code, r), tag)
        cabin_said, cabin_msa = said(lambda r: words.cabin(cabin, r), tag)
        basis, basis_msa = said(words.FARE_BASIS.__getitem__, tag)
        empty = sum(1 for d in found if d.fare is None)
        answer = Calendar(
            route_said=route,
            route_said_msa=route_msa,
            month_said=None if month is None else words.month(month, register(tag)),
            first=date_said(first, tag),
            last=date_said(last, tag),
            cabin=cabin,
            cabin_said=cabin_said,
            cabin_said_msa=cabin_msa,
            days=days,
            highest_sar=max(d.fare for d in found if d.fare is not None),
            no_flight_days=empty or None,
            fare_basis_said=basis,
            fare_basis_said_msa=basis_msa,
        )
        title = route_title(start.code, end.code, tag)
        return result(answer, calendar_card(answer, title, tag))

    return find


def calendar_card(answer: Calendar, route: str, tag: Tag) -> Card:
    """The calendar's card: the route and the span, then each of the seven days with its fare,
    the three said marked."""
    first = date.fromisoformat(answer.first.iso)
    if arabic(tag):
        span = f"في {answer.month_said}" if answer.month_said else f"من {day_title(first, tag)}"
        title = f"{route}، أرخص الأيام {span}"
    else:
        span = f"in {answer.month_said}" if answer.month_said else f"from {day_title(first, tag)}"
        title = f"{route}, cheapest days {span}"
    steps = []
    for d in answer.days:
        step = f"{day_title(date.fromisoformat(d.date.iso), tag)}: {money(d.fare_sar, tag)}"
        if d.mark:
            step += f"، {AMONG_AR}" if arabic(tag) else f", {AMONG_EN}"
        steps.append(step)
    return Card(title=title, steps=tuple(steps))
