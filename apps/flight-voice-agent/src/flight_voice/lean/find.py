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
  outbound segment; on the real network, the return's with the outbound's pick kept beside it
  once that pick is kept (find_return.py), and a listing that leaves flights out (`more`), for
  every airline, notes that one airline's flights come from another search (`MORE_REAL`).
- **The trip's two ways, on the real network** (find_return.py's `planned`): a one-way search
  back from the trip's destination to its origin, on or after its day out, is the trip's
  return while its way out is listed (`as_return`: the outbound's listing and pick kept, an
  airline asked narrowing the way back alone); a search for the way out with no return day
  keeps a round trip round, the way back following the new destination on its day (asked again
  when that day is before the new day out); `one_way` makes the trip one way. With the
  outbound chosen, the way back's flights are those leaving at least two hours after it lands
  (turnaround.py), and a return pick that no longer does is dropped (`RETURN_DROPPED`).
- **A span** (span.py): nothing is written to the trip; on the real network, with
  `flights_per_day` each day is searched and summed up (its flights, lowest and highest
  prices, first and last departures, airlines), for a question beyond each day's cheapest.

On the mock, the search is as run F reads it, before plan 011's round 2: no `flights_per_day`
or `one_way` in its schema (find_schema.py), no way back read as the return, a search with no
return day one way, the outbound's card. Its progress line is due at once there (run F's
timing) and after about 1.5 s on the real network (`PROGRESS_LIVE_AT_S`), so a fast or cached
answer never opens with it. The parameters' descriptions are in find_schema.py.

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
from flight_voice.lean.draft import LegKind, searched
from flight_voice.lean.find_dates import date_problem, refused
from flight_voice.lean.find_legs import (
    both_legs,
    named,
    nearest,
    no_flights,
    not_served,
    refused_answer,
    unknown_place,
)
from flight_voice.lean.find_return import (
    Planned,
    ReturnDay,
    kept_ids,
    lost_picks,
    planned,
    return_card,
    trip_notes,
    way_back,
)
from flight_voice.lean.find_schema import (
    AIRLINE,
    CABIN,
    CITY,
    DEPART,
    ONE_WAY,
    ORIGIN,
    PER_DAY,
    RETURN_REAL,
    TRAVELERS,
    as_run_f,
)
from flight_voice.lean.offer_cards import options_card, row_links
from flight_voice.lean.picking import Lost
from flight_voice.lean.results import (
    SEARCH_DOWN,
    LegList,
    _Data,
    fares_are,
    full_note,
    lean_result,
    route_said,
)
from flight_voice.lean.said_days import draft_end, held_days
from flight_voice.lean.span import DaySpan, SpanAsked, span_search
from flight_voice.lean.turnaround import RETURN_DROPPED, kept_return
from flight_voice.lean.weekday import SAID_BACK, SAID_OUT, Weekday, next_weekday, on_weekday
from flight_voice.persona import PROGRESS_AT_S, PROGRESS_LIVE_AT_S
from flight_voice.said import Tag
from flight_voice.tools.results import SEARCH_FAILED

FIND_FLIGHTS: Final = "find_flights"
DESCRIPTION: Final = (
    "Find the flights of a trip: the day they leave's flights, with the day they come back, "
    "or what flies over a span of days. Call it as soon as you know where the caller goes and "
    "the day they leave."
)
LOST: Final = "A flight chosen before is no longer offered with seats for everyone: choose again."
# On the real network, a day's options are some of its flights (plan 011: asked for flyadeal
# after a listing of 6 of 15, the model once answered from the 2 it was given, of 4).
MORE_REAL: Final = (
    "options are only some of the day's flights: for one airline's, call find_flights again "
    "with airline (instant)."
)
# A search waits for the slower of its legs; the library's default limit is 5 s.
TIMEOUT_S: Final = 25.0


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
    real = deps.network == "real"

    @tool(
        name=FIND_FLIGHTS,
        description=DESCRIPTION,
        progress="searching_live" if real else "searching",
        progress_after_s=PROGRESS_LIVE_AT_S if real else PROGRESS_AT_S,
        timeout_s=TIMEOUT_S,
    )
    async def find(
        ctx: CallContext,
        destination: Annotated[str, Field(min_length=1, max_length=40, description=CITY)],
        depart: Annotated[date | DaySpan, Field(description=DEPART)],
        origin: Annotated[str | None, Field(max_length=40, description=ORIGIN)] = None,
        return_date: Annotated[date | None, Field(description=RETURN_REAL)] = None,
        cabin: Annotated[Cabin | None, Field(description=CABIN)] = None,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=TRAVELERS)] = None,
        depart_weekday: Annotated[Weekday | None, Field(description=SAID_OUT)] = None,
        return_weekday: Annotated[Weekday | None, Field(description=SAID_BACK)] = None,
        airline: Annotated[str | None, Field(max_length=40, description=AIRLINE)] = None,
        flights_per_day: Annotated[bool, Field(description=PER_DAY)] = False,
        one_way: Annotated[bool, Field(description=ONE_WAY)] = False,
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
        plan: Planned | None = None
        if real and not isinstance(depart, DaySpan):  # the trip's two ways (find_return.py)
            reverse = (start.code, end.code) == (draft_end(draft), draft.origin.code)
            if back is None and return_weekday is not None:  # the way back by its weekday
                if reverse:  # the way back's own search: its day is the weekday's
                    depart = on_weekday(depart, return_weekday, not_before=draft.depart or today)
                else:
                    back = next_weekday(return_weekday, after=depart)
            heard, day_out = ctx.heard, draft.depart
            depart, back = held_days(
                heard, depart, back, said=return_weekday, reverse=reverse, day_out=day_out
            )
            plan = planned(draft, start, end, depart, back, one_way=one_way)
            start, end, depart, back = plan.start, plan.end, plan.depart, plan.back
        turned = plan is not None and plan.turned
        if (problem := refused(depart, back, today, last)) is not None:
            return date_problem(problem, today, last, deps.network)
        kept: Cabin = draft.cabin if cabin is None else cabin
        party = draft.travelers if travelers is None else travelers
        try:
            if isinstance(depart, DaySpan):
                asked = SpanAsked(
                    deps.data, (start, end), kept, party, today, deps.network, tag, flights_per_day
                )
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
        out_airline = None if plan is None else plan.airline
        legs = both_legs(
            (out, home), airline, tag, party, deps.places, back_only=turned, out_airline=out_airline
        )
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
            one_way=False if plan is not None and plan.round_trip else None,
        )
        made, early = kept_return(change.draft) if real else (change.draft, None)
        deps.trips.put(ctx.call_id, made)
        deps.check.mark(ctx.call_id, made)
        said, msa = route_said((start, end), tag)
        basis, basis_msa = fares_are(
            tag, round_trip=not made.one_way, travelers=party, network=deps.network
        )
        home_back, shown = way_back(made, back, came, tag, deps.places, turned=turned, real=real)
        listed = (went.data, *([home_back] if isinstance(home_back, LegList) else []))
        some = real and airline is None and any(leg.more for leg in listed)
        notes = [
            full_note(listed, party, kept),
            LOST if change.lost else None,
            RETURN_DROPPED if early else None,
            MORE_REAL if some else None,
            *trip_notes(plan, made, home_back, end, tag),
        ]
        found = Found(
            route=said,
            route_msa=msa,
            fares_are=basis,
            fares_are_msa=basis_msa,
            cabin=kept,
            travelers=party,
            outbound=went.data,
            return_=home_back,
            chosen=kept_ids(made),
            lost=lost_picks(latest, (*change.lost, *(("return",) if early else ()))) or None,
            note=" ".join(n for n in notes if n) or None,
        )
        card = None
        if real and shown is not None:
            route = (start, end)
            card = return_card(made, went, shown, route, kept, deps.places, tag, deps.network)
        if card is None:
            links = row_links(went.listed.offers, tag, deps.network)
            card = options_card(
                "outbound", went.data.options, (start, end), depart, kept, tag, links=links
            )
        return lean_result(found, card)

    return find if real else as_run_f(find)
