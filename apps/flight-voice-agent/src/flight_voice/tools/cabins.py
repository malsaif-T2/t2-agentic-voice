"""`compare_cabins`: economy, business and first class side by side for one listed flight.

The talker names the flight as `choose_flight` does, by the caller's pick as they said it, never
a flight it worked out, read in code against the options last listed for the leg
(`nothing_listed` and `unclear_choice` as there). Each cabin comes with its fare on that flight,
one way, per person, and whether it has a seat for every traveler; first class is marked not
offered on an aircraft that has none. It changes nothing: the cabin is changed with
`change_trip`. A read that does not answer is a `ToolError` that says it failed, never "no
seats".
"""

from __future__ import annotations

from datetime import date
from functools import partial
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import CallContext, Card, CardRow, Tool, ToolError, ToolResult, tool

from flight_voice.airline.airports import Register
from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import CABINS, Cabin
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag, arabic, words
from flight_voice.tools.cards import day_title, money
from flight_voice.tools.listing import listed_again
from flight_voice.tools.picks import Choice, departure_of, pick
from flight_voice.tools.results import (
    SAY,
    SEARCH_FAILED,
    DateSaid,
    NothingListed,
    Unclear,
    _Result,
    date_said,
    result,
    said,
)
from flight_voice.trip import LegKind, TripBook

COMPARE_CABINS: Final = "compare_cabins"
DESCRIPTION: Final = (
    "Compare economy, business and first class for one listed flight. Pass the caller's pick as "
    "they said it: its number in the list, the cheapest, the earliest, the latest, the morning, "
    "afternoon or evening one, or its departure time."
)
_LEG: Final = "The leg of the flight: outbound, or return."
_CHOICE: Final = "The caller's pick, as they said it; never a flight you worked out."


class CabinFare(_Result):
    """One cabin on the flight: its name said, whether the aircraft has it, its fare one way per
    person, whether it has a seat for every traveler, and whether it is the trip's cabin now."""

    cabin: Cabin
    cabin_said: str
    cabin_said_msa: str | None = None
    offered: bool
    fare_sar: int | None = None
    seats_ok: bool | None = None
    current: Literal[True] | None = None


class Cabins(_Result):
    """The cabins of one listed flight on its day."""

    status: Literal["ok"] = "ok"
    leg: LegKind
    n: int
    flight: str
    aircraft: str
    date: DateSaid
    departs: str
    travelers: int
    cabins: tuple[CabinFare, ...]
    fare_basis_said: str
    fare_basis_said_msa: str | None = None
    say: str = SAY["cabins"]


def _cabin_said(cabin: Cabin, register: Register) -> str:
    return words.cabin(cabin, register)


def compare_cabins(airline: Airline, trips: TripBook) -> Tool:
    """The cabins of a listed flight, over the call's draft in `trips` (the module's
    docstring)."""

    @tool(name=COMPARE_CABINS, description=DESCRIPTION, progress="searching")
    async def compare(
        ctx: CallContext,
        leg: Annotated[LegKind, Field(description=_LEG)],
        choice: Annotated[Choice, Field(description=_CHOICE)],
    ) -> ToolResult:
        tag: Tag = ctx.language
        draft = trips.get(ctx.call_id)
        shown = draft.shown(leg)
        if not shown:
            return result(NothingListed(leg=leg))
        named = pick(choice, shown, draft.cabin, draft.travelers)
        if len(named) != 1:
            could = listed_again(
                named or shown,
                cabin=draft.cabin,
                travelers=draft.travelers,
                tag=tag,
                name=airline.flight_name,
            )
            return result(Unclear(leg=leg, options=could))
        (one,) = named
        flight = departure_of(one).flight
        try:
            flown = await airline.departures(flight.origin, flight.destination, one.day)
        except AirlineUnavailableError:
            raise ToolError(SEARCH_FAILED) from None
        d = next(d for d in flown if d.flight.number == one.flight)
        each = []
        for cabin in CABINS:
            name, name_msa = said(partial(_cabin_said, cabin), tag)
            price = fare(d, cabin)
            each.append(
                CabinFare(
                    cabin=cabin,
                    cabin_said=name,
                    cabin_said_msa=name_msa,
                    offered=price is not None,
                    fare_sar=price,
                    seats_ok=None
                    if price is None
                    else seats_left(flight, one.day, cabin) >= draft.travelers,
                    current=True if cabin == draft.cabin else None,
                )
            )
        basis, basis_msa = said(words.FARE_BASIS.__getitem__, tag)
        answer = Cabins(
            leg=leg,
            n=one.n,
            flight=airline.flight_name(flight.number),
            aircraft=flight.aircraft,
            date=date_said(one.day, tag),
            departs=d.departs_at.strftime("%H:%M"),
            travelers=draft.travelers,
            cabins=tuple(each),
            fare_basis_said=basis,
            fare_basis_said_msa=basis_msa,
        )
        return result(answer, cabins_card(answer, one.day, tag))

    return compare


def cabin_row(cabin: CabinFare, aircraft: str, tag: Tag) -> CardRow:
    """One cabin as a card's row: its name and its fare, "full" when it has no seat for every
    traveler, or "not offered on a 787-9"; marked `unavailable` then, else `chosen` when it is
    the trip's cabin now."""
    name = cabin.cabin_said if arabic(tag) else cabin.cabin_said[0].upper() + cabin.cabin_said[1:]
    if cabin.fare_sar is None:
        article = "an" if aircraft.startswith("A") else "a"
        missing = (
            f"غير متوفرة على {aircraft}" if arabic(tag) else f"not offered on {article} {aircraft}"
        )
        return CardRow(title=name, detail=missing, mark="unavailable")
    full = None if cabin.seats_ok else ("ممتلئة" if arabic(tag) else "full")
    return CardRow(
        title=name,
        detail=full,
        value=money(cabin.fare_sar, tag),
        mark="unavailable" if full else ("chosen" if cabin.current else None),
    )


def cabins_card(answer: Cabins, day: date, tag: Tag) -> Card:
    """The cabins' card: the flight and its day, then a row for each cabin."""
    if arabic(tag):
        title = f"الدرجات على رحلة {answer.flight}، {day_title(day, tag)}"
    else:
        title = f"Cabins on flight {answer.flight}, {day_title(day, tag)}"
    rows = tuple(cabin_row(c, answer.aircraft, tag) for c in answer.cabins)
    return Card(title=title, rows=rows)
