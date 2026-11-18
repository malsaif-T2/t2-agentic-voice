"""`find_flights`, the lean agent's search: a day's flights, or what flies over a span of days.

The model passes the city in any language, or its code, the dates it worked out from the
calendar in its prompt (the day they leave as an ISO date, or a span of at most `MOST_DAYS` days,
`DaySpan`, and the day they come back, or none for one way or not yet known), and optionally the
airline the caller asked for. In order: a place the mock does not serve is `not_served` (with
the cities it serves), a place the directory does not know `unknown_place`; the dates
(find_dates.py's `date_problem`, between today and the source's last day); then the source's
answer: a route the mock does not fly `not_served`, a cabin it does not sell
`cabin_not_offered`, a day with no flight `no_flights` (with the nearest days that have one),
a bare code the provider answered nothing for `unknown_place`. A weekday the caller said is
held over its date (weekday.py). Then:

- **A day:** the route, the cabin, the travelers, the prices' basis (`fares_are`) and the
  outbound flights (find_legs.py), with the return's day alone when a return is given: its
  flights come with `choose_flights` once the outbound is chosen, one leg at a time, as a phone
  agent gives them, or with its `list_leg` when the caller asks about the way back first (given
  both days side by side, the model listed both in one reply and took one pick for both legs:
  f-dev-lean-4). Both legs are searched at once; a way back that could not be checked is
  `unknown` beside the outbound, and a second search checks it. A search that keeps a leg's pick
  (its route and day the same, the offer still answered with seats) names it in `chosen`, by
  its id, and a pick it drops in `lost`; with the outbound chosen it gives the return's flights.
  The call's trip is read again after the search (another tool may have written it meanwhile),
  takes the search in one assignment, and is marked for the booking check. Its card is the
  outbound segment.
- **A span** (span.py): nothing is written to the trip.

A source that does not answer is a `ToolError` that says the search failed (`SEARCH_DOWN` when
it will not answer again soon), never "no flights".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import CallContext, Tool, ToolError, ToolResult, tool

from flight_voice.flight_data.model import Cabin
from flight_voice.flight_data.port import FlightDataUnavailableError, trip_days
from flight_voice.flight_data.queries import DayOffers, OfferQuery
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LEGS, LeanDraft, LegKind, searched
from flight_voice.lean.find_dates import date_problem, refused
from flight_voice.lean.find_legs import (
    Built,
    both_legs,
    named,
    nearest,
    no_flights,
    not_served,
    refused_answer,
    unknown_place,
)
from flight_voice.lean.offer_cards import options_card
from flight_voice.lean.picking import Lost
from flight_voice.lean.results import (
    SEARCH_DOWN,
    Day,
    LegList,
    _Data,
    day_of,
    fares_are,
    full_note,
    lean_result,
    route_said,
)
from flight_voice.lean.span import DaySpan, SpanAsked, span_search
from flight_voice.lean.weekday import SAID, Weekday, on_weekday
from flight_voice.persona import PROGRESS_AT_S
from flight_voice.said import Tag
from flight_voice.tools.results import SEARCH_FAILED

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
_AIRLINE: Final = (
    "An airline the caller asked for, by its name in any language or its code; null for every "
    "airline."
)
RETURN_LISTED: Final = (
    "Its flights come with choose_flights once the outbound is chosen, or with its list_leg "
    "when the caller asks about the way back first."
)
RETURN_KEPT: Final = "The return flight chosen before is kept; its id is in chosen."
RETURN_UNKNOWN: Final = (
    "The way back could not be checked just now; once the way out is chosen, call find_flights "
    "again with the same days to check it."
)
LOST: Final = "A flight chosen before is no longer offered with seats for everyone: choose again."
# A search waits for the slower of its legs; the library's default limit is 5 s.
TIMEOUT_S: Final = 25.0


class ReturnDay(_Data):
    """A round trip's return as a search gives it before the outbound is chosen: its day alone,
    or that it could not be checked (the module's docstring)."""

    status: Literal["unknown"] | None = None
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
    lost: tuple[Lost, ...] | None = None
    note: str | None = None


def find_flights(deps: LeanDeps) -> Tool:
    """The search over `deps`' source, writing each call's trip and marking it for the booking
    check (the module's docstring)."""
    progress = "searching" if deps.network == "mock" else "searching_live"

    @tool(
        name=FIND_FLIGHTS,
        description=DESCRIPTION,
        progress=progress,
        progress_after_s=PROGRESS_AT_S,
        timeout_s=TIMEOUT_S,
    )
    async def find(
        ctx: CallContext,
        destination: Annotated[str, Field(min_length=1, max_length=40, description=_CITY)],
        depart: Annotated[date | DaySpan, Field(description=_DEPART)],
        origin: Annotated[str | None, Field(max_length=40, description=_ORIGIN)] = None,
        return_date: Annotated[date | None, Field(description=_RETURN)] = None,
        cabin: Annotated[Cabin | None, Field(description=_CABIN)] = None,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=_TRAVELERS)] = None,
        depart_weekday: Annotated[Weekday | None, Field(description=SAID)] = None,
        return_weekday: Annotated[Weekday | None, Field(description=SAID)] = None,
        airline: Annotated[str | None, Field(max_length=40, description=_AIRLINE)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        draft = deps.trips.get(ctx.call_id)
        today = deps.today()
        last = deps.data.last_day(today)
        if isinstance(depart, DaySpan) and depart.first == depart.last:
            # A span of one day is that day: its flights, with ids to choose (the owner's call
            # of 2026-11-18, where a one-day span gave no flight to book).
            depart = depart.first
        if not isinstance(depart, DaySpan):
            depart = on_weekday(depart, depart_weekday, not_before=today)
            if return_date is not None:
                return_date = on_weekday(return_date, return_weekday, not_before=depart)
        end = deps.places.find(destination)
        start = draft.origin if origin is None else deps.places.find(origin)
        if end is None or start is None:
            if deps.places.served is not None:
                return not_served(deps.places, tag)
            return unknown_place("destination" if end is None else "origin")
        back = None if isinstance(depart, DaySpan) else return_date
        if (problem := refused(depart, back, today, last)) is not None:
            return date_problem(problem, today, last, deps.network)
        kept: Cabin = draft.cabin if cabin is None else cabin
        party = draft.travelers if travelers is None else travelers
        try:
            if isinstance(depart, DaySpan):
                asked = SpanAsked(deps.data, (start, end), kept, party, today, deps.network, tag)
                spanned = await span_search(asked, depart)
                if isinstance(spanned, ToolResult):
                    return spanned
                if spanned.get("status") == "not_served":
                    return not_served(deps.places, tag)
                return lean_result(spanned)
            out_q = OfferQuery(origin=start, destination=end, day=depart, cabin=kept, adults=party)
            back_q = (
                None
                if back is None
                else out_q.model_copy(update={"origin": end, "destination": start, "day": back})
            )
            out, home = await trip_days(deps.data, out_q, back_q)
        except FlightDataUnavailableError as error:
            raise ToolError(SEARCH_DOWN if error.lasting else SEARCH_FAILED) from None
        refusal = refused_answer(out, deps.places, tag)
        if refusal is not None:
            return refusal
        end, start = named(end, out), named(start, out)
        if out.status == "no_flights" and not (start.known and end.known):
            return unknown_place("destination" if not end.known else "origin")
        for day, answer in ((depart, out), (back, home)):
            if day is not None and isinstance(answer, DayOffers) and answer.status == "no_flights":
                return no_flights(day, await nearest(deps.data, answer.query, today), tag)
        legs = both_legs((out, home), airline, tag, party, deps.places)
        if isinstance(legs, dict):
            return lean_result(legs)
        went, came = legs
        latest = deps.trips.get(ctx.call_id)  # another tool may have written it meanwhile
        change = searched(
            latest,
            origin=start,
            destination=end,
            depart=depart,
            return_date=back,
            travelers=party,
            cabin=kept,
            out=(out, went.listed),
            back=None if came is None or not isinstance(home, DayOffers) else (home, came.listed),
        )
        made = change.draft
        deps.trips.put(ctx.call_id, made)
        deps.check.mark(ctx.call_id, made)
        said, msa = route_said((start, end), tag)
        basis, basis_msa = fares_are(
            tag, round_trip=back is not None, travelers=party, network=deps.network
        )
        way_back = _return(made, back, came, tag)
        listed = (went.data, *([way_back] if isinstance(way_back, LegList) else []))
        notes = [full_note(listed, party, kept), LOST if change.lost else None]
        found = Found(
            route=said,
            route_msa=msa,
            fares_are=basis,
            fares_are_msa=basis_msa,
            cabin=kept,
            travelers=party,
            outbound=went.data,
            return_=way_back,
            chosen=_kept(made),
            lost=_lost(latest, change.lost) or None,
            note=" ".join(n for n in notes if n) or None,
        )
        card = options_card("outbound", went.data.options, (start, end), depart, kept, tag)
        return lean_result(found, card)

    return find


def _return(
    made: LeanDraft, back: date | None, home: Built | None, tag: Tag
) -> LegList | ReturnDay | None:
    """A round trip's return as the search gives it: its flights when the outbound's pick is
    kept, else its day alone, saying so when the return's pick is kept or it could not be
    checked (the module's docstring)."""
    if back is None:
        return None
    if home is None:
        return ReturnDay(status="unknown", day=day_of(back, tag), note=RETURN_UNKNOWN)
    if made.chosen_outbound is not None:
        return home.data
    note = RETURN_LISTED if made.chosen_return is None else RETURN_KEPT
    return ReturnDay(day=day_of(back, tag), note=note)


def _kept(made: LeanDraft) -> dict[LegKind, str] | None:
    """The legs whose pick the search kept, by their ids; None when it kept none."""
    kept = {leg: pick.id for leg in LEGS if (pick := made.chosen(leg)) is not None}
    return kept or None


def _lost(before: LeanDraft, legs: tuple[LegKind, ...]) -> tuple[Lost, ...]:
    """The picks a search dropped, by their departure times."""
    found = ((leg, before.chosen(leg)) for leg in legs)
    return tuple(Lost(leg=leg, departs=o.departs.strftime("%H:%M")) for leg, o in found if o)
