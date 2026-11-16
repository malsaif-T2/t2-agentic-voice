"""`search_flights`: the caller's trip searched and its outbound flights listed.

The talker passes the city as the caller said it and each date as a date form (`DateSpec`); the
code finds the airport, resolves the dates against today in Riyadh and checks, in order: the
cities are served (`not_served`); the route is flown, every route starting or ending in Riyadh
(`not_served`); the departure resolves inside the booking window (`date_problem`); a round trip
has a return date (`needs_return_date`, nothing searched) that resolves, not before the
departure (`date_problem`); the cabin is sold on the route (`cabin_not_offered`); each leg's day
has a flight (`no_flights_that_day`, with the two nearest days that have one); a flight that day
has a seat for every traveler in the cabin (`no_seats`, with the cabins that do). Then the
outbound flights are listed, and the call's draft takes the search's route, dates, travelers and
cabin and the options in the order said, in one assignment, its last step.

A search that does not answer is a `ToolError` that says it failed (`SEARCH_FAILED`), never "no
flights".
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Final

from pydantic import Field
from t2_agentic_voice import CallContext, Tool, ToolError, ToolResult, tool

from flight_voice.airline.airports import Airport, airport, find_airport, served_cities
from flight_voice.airline.dates import (
    DateProblem,
    DateSpec,
    Resolved,
    resolve_departure,
    resolve_return,
)
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import (
    CABINS,
    Cabin,
    Departure,
    flies_on,
    flights,
    route_served,
    window,
)
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag
from flight_voice.tools import cards
from flight_voice.tools.results import (
    SAY,
    SEARCH_FAILED,
    CabinNotOffered,
    DateIssue,
    NeedsReturn,
    NoFlights,
    NoSeats,
    NotServed,
    date_said,
    listable,
    listing,
    options,
    result,
    said,
)
from flight_voice.trip import LegKind, Shown, TripBook, TripDraft

SEARCH_FLIGHTS: Final = "search_flights"
DESCRIPTION: Final = (
    "Find flights for the caller's trip and list them. Call it as soon as you know where they "
    "go and when they leave, and, for a round trip, when they come back. Pass the city as the "
    "caller said it and dates as date forms; never work out a date yourself. Fares are one way, "
    "per person, in Saudi riyals."
)
_CITY: Final = "The city as the caller said it, in their words."
_ORIGIN: Final = "The city they leave from, only when it is not Riyadh."
_DEPART: Final = "The day they leave, as a date form."
_RETURN: Final = "The day they come back, as a date form; leave it out for a one-way trip."
_ONE_WAY: Final = "True only when the caller wants a one-way trip."
_TRAVELERS: Final = "How many people travel, when the caller said; else leave it out."
_CABIN: Final = "The cabin, when the caller named one; else leave it out."
# How many days with a flight a `no_flights_that_day` result offers.
NEAREST: Final = 2


def nearest_days(origin: Airport, destination: Airport, day: date, today: date) -> list[date]:
    """The `NEAREST` days closest to `day`, inside the booking window, that the route flies,
    the earlier first of two as close."""
    first, last = window(today)
    found: list[date] = []
    for step in range(1, (last - first).days + 1):
        for near in (day - timedelta(days=step), day + timedelta(days=step)):
            if first <= near <= last and flies_on(origin.code, destination.code, near):
                found.append(near)
        if len(found) >= NEAREST:
            break
    return sorted(found[:NEAREST])


def _problem(issue: DateProblem, leg: LegKind, tag: Tag) -> ToolResult:
    return result(
        DateIssue(
            leg=leg,
            problem=issue.problem,
            last_day=date_said(issue.last_day, tag),
            say=SAY[issue.problem],
        )
    )


def _not_served(why: str, tag: Tag) -> ToolResult:
    served, served_msa = said(served_cities, tag)
    return result(NotServed(served_said=served, served_said_msa=served_msa, say=SAY[why]))


def search_flights(airline: Airline, trips: TripBook) -> Tool:
    """The search over `airline`, writing each call's draft in `trips` (the module's
    docstring)."""

    @tool(name=SEARCH_FLIGHTS, description=DESCRIPTION, progress="searching")
    async def search(
        ctx: CallContext,
        destination: Annotated[str, Field(min_length=1, max_length=40, description=_CITY)],
        depart: Annotated[DateSpec, Field(description=_DEPART)],
        origin: Annotated[str | None, Field(max_length=40, description=_ORIGIN)] = None,
        return_date: Annotated[DateSpec | None, Field(description=_RETURN)] = None,
        one_way: Annotated[bool, Field(description=_ONE_WAY)] = False,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=_TRAVELERS)] = None,
        cabin: Annotated[Cabin | None, Field(description=_CABIN)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        draft = trips.get(ctx.call_id)
        today = airline.today()
        end = find_airport(destination)
        start = airport(draft.origin) if origin is None else find_airport(origin)
        if end is None or start is None:
            return _not_served("not_served_city", tag)
        if not route_served(start.code, end.code):
            return _not_served("not_served_route", tag)
        out = resolve_departure(depart, today)
        if isinstance(out, DateProblem):
            return _problem(out, "outbound", tag)
        party = travelers if travelers is not None else draft.travelers
        kept: Cabin = cabin if cabin is not None else draft.cabin
        back: Resolved | None = None
        if not one_way:
            if return_date is None:
                asked = _searched(draft, start, end, (out.day, None), False, party, kept)
                trips.put(ctx.call_id, asked)
                return result(NeedsReturn())
            returning = resolve_return(return_date, out.day, today)
            if isinstance(returning, DateProblem):
                return _problem(returning, "return", tag)
            back = returning
        sold = flights(start.code, end.code)[0].cabins
        if kept not in sold:
            offered = tuple(c for c in CABINS if c in sold)
            return result(CabinNotOffered(cabin=kept, offered=offered))
        try:
            outs = await airline.departures(start.code, end.code, out.day)
            backs = () if back is None else await airline.departures(end.code, start.code, back.day)
        except AirlineUnavailableError:
            raise ToolError(SEARCH_FAILED) from None
        empty = _no_flights("outbound", start, end, out.day, outs, today, tag)
        if empty is None and back is not None:
            empty = _no_flights("return", end, start, back.day, backs, today, tag)
        if empty is not None:
            return empty
        found = listable(outs, kept)
        listed = options(found, cabin=kept, travelers=party, tag=tag, name=airline.flight_name)
        if not any(o.seats_ok for o in listed):
            return _no_seats(found, out.day, kept, party, tag)
        answer = listing(
            "outbound",
            (start.code, end.code),
            out.day,
            listed,
            travelers=party,
            cabin=kept,
            tag=tag,
            assumed=out.assumed,
            return_date=None if back is None else date_said(back.day, tag, assumed=back.assumed),
        )
        shown = tuple(
            Shown(n=o.n, flight=d.flight.number, day=out.day)
            for o, d in zip(listed, found, strict=True)
        )
        back_day = None if back is None else back.day
        made = _searched(draft, start, end, (out.day, back_day), one_way, party, kept)
        trips.put(ctx.call_id, made.listed("outbound", shown))
        card = cards.listing_card(answer, start.code, end.code, out.day, tag)
        return result(answer, card)

    return search


def _no_flights(
    leg: LegKind,
    start: Airport,
    end: Airport,
    day: date,
    flown: tuple[Departure, ...],
    today: date,
    tag: Tag,
) -> ToolResult | None:
    """`no_flights_that_day` for a leg whose day has no flight, with the nearest days that
    have one; `None` when it has a flight."""
    if flown:
        return None
    near = nearest_days(start, end, day, today)
    return result(
        NoFlights(leg=leg, date=date_said(day, tag), nearest=tuple(date_said(d, tag) for d in near))
    )


def _no_seats(
    found: tuple[Departure, ...], day: date, cabin: Cabin, travelers: int, tag: Tag
) -> ToolResult:
    """`no_seats` for a day whose flights are short of seats in `cabin`, with the other cabins
    some flight that day has seats in for every traveler."""
    sold = found[0].flight.cabins
    with_seats = tuple(
        c
        for c in sold
        if c != cabin and any(seats_left(d.flight, day, c) >= travelers for d in found)
    )
    return result(
        NoSeats(
            leg="outbound",
            date=date_said(day, tag),
            cabin=cabin,
            travelers=travelers,
            cabins_with_seats=with_seats,
        )
    )


def _searched(
    draft: TripDraft,
    start: Airport,
    end: Airport,
    days: tuple[date, date | None],
    one_way: bool,
    travelers: int,
    cabin: Cabin,
) -> TripDraft:
    return draft.searched(
        origin=start.code,
        destination=end.code,
        depart=days[0],
        return_date=days[1],
        one_way=one_way,
        travelers=travelers,
        cabin=cabin,
    )
