"""`find_flights`, the lean agent's search: a day's flights, or what flies over a span of days.

The model passes the city in any language, or its code, and the dates it worked out from the
calendar in its prompt: the day they leave as an ISO date, or a span of at most `MOST_DAYS`
days (`DaySpan`), and the day they come back, or none for one way or not yet known. The airline's
window still judges every date: a day before today or past the booking window, a return before
its departure, and a span too long or the wrong way round are a `date_problem` naming the window
(`first_day`, `last_day`), with a short note. The checks, in order: the cities are served and
the route is flown (`not_served`, with the cities served); the dates; the cabin is sold on the
route (`cabin_not_offered`); each day has a flight (`no_flights`, with the nearest days that
have one). Then:

- **A day:** the route, the cabin, the travelers, the fares' basis (`fares_are`: per person,
  each way on a round trip; results.py) and the outbound flights (results.py's `LegList`), with
  the return's day alone when a return is given (`ReturnDay`): its flights come with
  `choose_flights` once the outbound is chosen (choose.py's `listed`), one leg at a time, as a
  phone agent gives them, or with its `list_leg` when the caller asks about the way back first.
  Given both days' flights side by side, the model listed both in one reply, over the words a
  reply may have, and took one pick for both legs (f-dev-lean-4: 34 of 38 round-trip listings,
  and f30's and f09's wrong bookings). A search that keeps a leg's pick (its route and day the
  same: a new return day after the outbound pick) names it in `chosen`, by its id, and with
  the outbound chosen gives the return's flights (`LegList`); with the return's pick alone
  kept, its day says so. A full flight in a leg listed has a note. The call's trip takes the
  route, the days, the travelers, the cabin and both legs' options, in one assignment, and is
  marked for the booking check; a search with no return makes it one way. Its card is the
  outbound segment; the return segment's comes once the outbound is chosen.
- **A span** (span.py), of up to two months: the route's daily departure times and the two
  cheapest days with their fares; for two weeks or less each day with its weekday, its flight
  count and its lowest fare and the days with no flight, for longer each week's days with a
  flight and its cheapest day. Nothing is written to the trip. Its card is the outbound
  segment's calendar of days.

A search that does not answer is a `ToolError` that says it failed, never "no flights".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal

from pydantic import Field, JsonValue
from t2_agentic_voice import CallContext, Tool, ToolError, ToolResult, tool

from flight_voice.airline.airports import Airport, airport, find_airport, served_cities
from flight_voice.airline.schedule import CABINS, Cabin, Departure, flights, route_served, window
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.choose import LEGS
from flight_voice.lean.results import (
    Built,
    Day,
    LegList,
    _Data,
    day_of,
    fares_are,
    full_note,
    lean_result,
    leg_list,
    leg_options,
    option_id,
    route_said,
)
from flight_voice.lean.span import MOST_DAYS, DaySpan, span_search
from flight_voice.persona import PROGRESS_AT_S
from flight_voice.said import Tag, register
from flight_voice.tools import cards
from flight_voice.tools.results import SEARCH_FAILED
from flight_voice.tools.search import nearest_days
from flight_voice.trip import LegKind, TripBook, TripDraft

FIND_FLIGHTS: Final = "find_flights"
DESCRIPTION: Final = (
    "Find the flights of a trip: the day they leave's flights, with the day they come back, "
    "or what flies over a span of days. Call it as soon as you know where the caller goes and "
    "the day they leave."
)
_CITY: Final = "The city they go to, in any language, or its code."
_ORIGIN: Final = "The city they leave from; Riyadh unless they said another."
_DEPART: Final = (
    "The day they leave, YYYY-MM-DD, from the calendar; or a span of at most two months they "
    "asked about without naming one day."
)
_RETURN: Final = "The day they come back, YYYY-MM-DD; null for one way or not said yet."
_CABIN: Final = "economy, business or first; the trip's own (economy at first) when not said."
_TRAVELERS: Final = "How many travel, 1 to 9; the trip's own (1 at first) when not said."
Problem = Literal["past", "beyond_window", "return_before_departure", "span_too_long"]
_NOTES: Final[dict[Problem, str]] = {
    "past": "That day has passed.",
    "beyond_window": "Bookings are open only up to last_day.",
    "return_before_departure": (
        "The day back comes before the day out: a return must be on or after the departure."
    ),
    "span_too_long": f"A span is {MOST_DAYS} days at most, its first day before its last.",
}
_NOT_SERVED: Final = "Every flight starts or ends in Riyadh."
RETURN_LISTED: Final = (
    "Its flights come with choose_flights once the outbound is chosen, or with its list_leg "
    "when the caller asks about the way back first."
)
RETURN_KEPT: Final = "The return flight chosen before is kept; its id is in chosen."


class ReturnDay(_Data):
    """A round trip's return as a search gives it before the outbound is chosen: its day alone
    (the module's docstring)."""

    day: Day
    note: str = RETURN_LISTED


class Found(_Data):
    """A day's flights (the module's docstring)."""

    status: Literal["ok"] = "ok"
    route: str
    route_msa: str | None = None
    cabin: Cabin
    travelers: int
    fares_are: str
    fares_are_msa: str | None = None
    outbound: LegList
    return_: LegList | ReturnDay | None = Field(default=None, alias="return")
    chosen: dict[LegKind, str] | None = None
    note: str | None = None


def date_problem(problem: Problem, today: date) -> ToolResult:
    """A date the window refuses: why, the window's first and last days, and a short note."""
    first, last = window(today)
    answer: dict[str, JsonValue] = {"status": "date_problem", "problem": problem}
    answer |= {"first_day": first.isoformat(), "last_day": last.isoformat()}
    return lean_result(answer | {"note": _NOTES[problem]})


def no_flights(day: date, near: list[date], tag: Tag) -> ToolResult:
    """A day with no flight, and the nearest days that have one."""
    nearest: list[JsonValue] = [day_of(n, tag).model_dump() for n in near]
    return lean_result({"status": "no_flights", "day": day.isoformat(), "nearest": nearest})


def _not_served(tag: Tag) -> ToolResult:
    served = served_cities(register(tag))
    return lean_result({"status": "not_served", "served": served, "note": _NOT_SERVED})


def _refused(depart: date | DaySpan, back: date | None, today: date) -> Problem | None:
    """Why the window refuses the dates, or None (the module's docstring)."""
    first, last = window(today)
    start, end = (depart.first, depart.last) if isinstance(depart, DaySpan) else (depart, depart)
    if isinstance(depart, DaySpan) and not 0 <= (end - start).days < MOST_DAYS:
        return "span_too_long"
    if end < first:
        return "past"
    if start > last or (back is not None and back > last):
        return "beyond_window"
    if back is not None and back < start:
        return "return_before_departure"
    return None


def find_flights(airline: Airline, trips: TripBook, check: BookingCheck) -> Tool:
    """The search over `airline`, writing each call's trip in `trips` and marking it in `check`
    (the module's docstring)."""

    @tool(
        name=FIND_FLIGHTS,
        description=DESCRIPTION,
        progress="searching",
        progress_after_s=PROGRESS_AT_S,
    )
    async def find(
        ctx: CallContext,
        destination: Annotated[str, Field(min_length=1, max_length=40, description=_CITY)],
        depart: Annotated[date | DaySpan, Field(description=_DEPART)],
        origin: Annotated[str | None, Field(max_length=40, description=_ORIGIN)] = None,
        return_date: Annotated[date | None, Field(description=_RETURN)] = None,
        cabin: Annotated[Cabin | None, Field(description=_CABIN)] = None,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=_TRAVELERS)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        draft = trips.get(ctx.call_id)
        today = airline.today()
        end = find_airport(destination)
        start = airport(draft.origin) if origin is None else find_airport(origin)
        if end is None or start is None or not route_served(start.code, end.code):
            return _not_served(tag)
        back = None if isinstance(depart, DaySpan) else return_date
        if (problem := _refused(depart, back, today)) is not None:
            return date_problem(problem, today)
        kept: Cabin = draft.cabin if cabin is None else cabin
        party = draft.travelers if travelers is None else travelers
        sold = flights(start.code, end.code)[0].cabins
        if kept not in sold:
            offered: list[JsonValue] = [c for c in CABINS if c in sold]
            return lean_result({"status": "cabin_not_offered", "cabin": kept, "offered": offered})
        try:
            if isinstance(depart, DaySpan):
                return await span_search(airline, (start, end), depart, kept, tag)
            outs, backs = await airline.trip_departures(start.code, end.code, depart, back)
        except AirlineUnavailableError:
            raise ToolError(SEARCH_FAILED) from None
        for day, flown, way in ((depart, outs, (start, end)), (back, backs, (end, start))):
            if day is not None and not flown:
                return no_flights(day, nearest_days(*way, day, today), tag)
        legs = _Day(airline, kept, party, tag)
        out, home = legs.built(outs), None if back is None else legs.built(backs)
        made = _written(draft, (start, end), (depart, back), (kept, party), (out, home))
        trips.put(ctx.call_id, made)
        check.mark(ctx.call_id, made)
        said, msa = route_said((start.code, end.code), tag)
        basis, basis_msa = fares_are(tag, round_trip=back is not None)
        outbound, way_back = leg_list(depart, out, tag), _return(made, back, home, tag)
        listed = (outbound, *([way_back] if isinstance(way_back, LegList) else []))
        found = Found(
            route=said,
            route_msa=msa,
            fares_are=basis,
            fares_are_msa=basis_msa,
            cabin=kept,
            travelers=party,
            outbound=outbound,
            return_=way_back,
            chosen=_kept(made, airline.code),
            note=full_note(listed, party, kept),
        )
        card = cards.options_card("outbound", out.card, (start.code, end.code), depart, kept, tag)
        return lean_result(found, card)

    return find


class _Day:
    """How a day's flights are built for one search: its airline, cabin, travelers and tag."""

    def __init__(self, airline: Airline, cabin: Cabin, travelers: int, tag: Tag) -> None:
        self.airline, self.cabin, self.travelers, self.tag = airline, cabin, travelers, tag

    def built(self, found: tuple[Departure, ...]) -> Built:
        return leg_options(
            found,
            cabin=self.cabin,
            travelers=self.travelers,
            tag=self.tag,
            code=self.airline.code,
            name=self.airline.flight_name,
        )


def _written(
    draft: TripDraft,
    route: tuple[Airport, Airport],
    days: tuple[date, date | None],
    party: tuple[Cabin, int],
    legs: tuple[Built, Built | None],
) -> TripDraft:
    """The trip with the search's route, days, cabin and travelers and its options listed."""
    (start, end), (depart, back), (cabin, travelers), (out, home) = route, days, party, legs
    made = draft.searched(
        origin=start.code,
        destination=end.code,
        depart=depart,
        return_date=back,
        one_way=back is None,
        travelers=travelers,
        cabin=cabin,
    ).listed("outbound", out.shown)
    return made if home is None else made.listed("return", home.shown)


def _return(
    made: TripDraft, back: date | None, home: Built | None, tag: Tag
) -> LegList | ReturnDay | None:
    """A round trip's return as the search gives it: its flights when the outbound's pick is
    kept, else its day alone, saying so when the return's pick is kept (the module's
    docstring)."""
    if back is None or home is None:
        return None
    if made.chosen_outbound is not None:
        return leg_list(back, home, tag)
    note = RETURN_LISTED if made.chosen_return is None else RETURN_KEPT
    return ReturnDay(day=day_of(back, tag), note=note)


def _kept(made: TripDraft, code: str) -> dict[LegKind, str] | None:
    """The legs whose pick the search kept, by their ids; None when it kept none."""
    picks = ((leg, made.chosen(leg)) for leg in LEGS)
    kept = {leg: option_id(code, pick.flight, pick.day) for leg, pick in picks if pick}
    return kept or None
