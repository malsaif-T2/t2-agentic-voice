"""`choose_flight`, the caller's pick of a listed flight, and `change_trip`, a change to the
travelers, the cabin or the trip's kind.

`choose_flight` reads the pick against the options last listed for the leg, in the order said
(`picks.py`): a leg with nothing listed is `nothing_listed`; a pick that names no option, or
several, is `unclear_choice` with the options it could mean; a picked flight short of seats for
every traveler is `no_seats`, with the cabins that have them and the other flights listed that
have seats. Then the leg is chosen, and what comes next is said: on a round trip whose return is
not chosen, the return day's flights, listed as a search lists them; once every leg is chosen,
the trip whole with its total, and the `say` that sends the talker straight to `book_trip`, so
the read-back is the one summary and the one confirmation.

`change_trip` changes the travelers, the cabin or one way and prices the chosen legs again: a
leg whose flight has too few seats for it now loses its choice, and its options are listed again
with their new fares; a complete trip goes straight to `book_trip`, as `choose_flight`'s does.

Each tool writes the call's draft once, as its last step; a search that does not answer is a
`ToolError` that says it failed, and the draft is left as it was.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import CallContext, Card, Tool, ToolError, ToolResult, tool

from flight_voice.airline.bookings import Leg
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import CABINS, Cabin, flights
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.said import Tag
from flight_voice.tools import cards
from flight_voice.tools.listing import listable, listed_again, listing, options
from flight_voice.tools.picks import Choice, departure_of, pick
from flight_voice.tools.results import (
    SAY,
    SEARCH_FAILED,
    CabinNotOffered,
    Listing,
    NoSeats,
    NothingListed,
    Option,
    Unclear,
    _Result,
    date_said,
    result,
)
from flight_voice.tools.trip_view import TripView, view
from flight_voice.trip import LegKind, Shown, TripBook, TripDraft, changed

CHOOSE_FLIGHT: Final = "choose_flight"
CHANGE_TRIP: Final = "change_trip"
CHOOSE_DESCRIPTION: Final = (
    "Pick the flight the caller chose for one leg, from the flights you listed. Pass their "
    "choice as they said it: its number in the list, the cheapest, the earliest, the latest, "
    "the morning, afternoon or evening one, or its departure time."
)
CHANGE_DESCRIPTION: Final = (
    "Change the trip the caller is planning: the number of travelers, the cabin, one way or "
    "round trip. For another day or city, call search_flights again."
)
NOTHING_TO_CHANGE: Final = (
    "Nothing was changed: pass travelers, cabin or one_way, the one the caller changed."
)
_LEG: Final = "The leg the caller chose for: outbound, or return."
_CHOICE: Final = "The caller's pick, as they said it; never a flight you worked out."
_TRAVELERS: Final = "How many people travel now, when the caller changed it."
_CABIN: Final = "The cabin the caller wants now, when they changed it."
_ONE_WAY: Final = "True for one way, false for a round trip, when the caller changed it."
Changeable = Literal["travelers", "cabin", "one_way"]


class Chosen(_Result):
    """A leg chosen: the trip so far, and the return flights when they are asked next."""

    status: Literal["ok"] = "ok"
    leg: LegKind
    trip: TripView
    returns: Listing | None = None
    say: str


class Changed(_Result):
    """A trip changed: what changed, the trip priced again, the legs that lost their choice,
    and the options of the leg the caller is asked about next, with their new fares."""

    status: Literal["ok"] = "ok"
    changed: tuple[Changeable, ...]
    trip: TripView
    lost: tuple[LegKind, ...] = ()
    leg: LegKind | None = None
    options: tuple[Option, ...] = ()
    say: str


def choose_flight(airline: Airline, trips: TripBook) -> Tool:
    """The pick of a listed flight, over the call's draft in `trips` (the module's docstring)."""

    @tool(name=CHOOSE_FLIGHT, description=CHOOSE_DESCRIPTION)
    async def choose(
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
            could = _again(named or list(shown), draft, airline, tag)
            return result(Unclear(leg=leg, options=could))
        (one,) = named
        if seats_left(departure_of(one).flight, one.day, draft.cabin) < draft.travelers:
            return _full(leg, one, draft, airline, tag)
        made = draft.choose(leg, Leg(flight=one.flight, day=one.day))
        try:
            made, answer, card = await _next(leg, made, airline, tag)
        except AirlineUnavailableError:
            raise ToolError(SEARCH_FAILED) from None
        trips.put(ctx.call_id, made)
        return result(answer, card)

    return choose


async def _next(
    leg: LegKind, draft: TripDraft, airline: Airline, tag: Tag
) -> tuple[TripDraft, Chosen, Card | None]:
    """What a choice of `leg` leads to: the trip whole, the return flights, or the question
    still to ask; the draft with the return flights listed when they are."""
    seen = view(draft, tag, airline.today(), airline.flight_name)
    if not draft.missing():
        return (
            draft,
            Chosen(leg=leg, trip=seen, say=SAY["complete"]),
            cards.trip_card(seen, draft, tag),
        )
    if leg == "return" and draft.chosen_outbound is None:
        chosen = Chosen(leg=leg, trip=seen, say=SAY["chosen_then_outbound"])
        return draft, chosen, cards.trip_card(seen, draft, tag)
    if draft.return_date is None or draft.destination is None:
        chosen = Chosen(leg=leg, trip=seen, say=SAY["chosen_needs_return"])
        return draft, chosen, cards.trip_card(seen, draft, tag)
    start, end, day = draft.destination, draft.origin, draft.return_date
    found = listable(await airline.departures(start, end, day), draft.cabin)
    listed = options(
        found, cabin=draft.cabin, travelers=draft.travelers, tag=tag, name=airline.flight_name
    )
    returns = listing(
        "return", (start, end), day, listed, travelers=draft.travelers, cabin=draft.cabin, tag=tag
    )
    say = SAY["chosen_then_return" if any(o.seats_ok for o in listed) else "chosen_return_full"]
    shown = tuple(
        Shown(n=o.n, flight=d.flight.number, day=day) for o, d in zip(listed, found, strict=True)
    )
    chosen = Chosen(leg=leg, trip=seen, returns=returns, say=say)
    card = cards.listing_card(returns, start, end, day, tag) if listed else None
    return draft.listed("return", shown), chosen, card


def _again(shown: list[Shown], draft: TripDraft, airline: Airline, tag: Tag) -> tuple[Option, ...]:
    return listed_again(
        shown, cabin=draft.cabin, travelers=draft.travelers, tag=tag, name=airline.flight_name
    )


def _full(leg: LegKind, one: Shown, draft: TripDraft, airline: Airline, tag: Tag) -> ToolResult:
    """`no_seats` for a picked flight short of seats in the draft's cabin: the cabins it has
    seats in for every traveler, and the other flights listed that have seats."""
    flight = departure_of(one).flight
    with_seats = tuple(
        c
        for c in flight.cabins
        if c != draft.cabin and seats_left(flight, one.day, c) >= draft.travelers
    )
    others = [s for s in draft.shown(leg) if s.n != one.n]
    selling = tuple(o for o in _again(others, draft, airline, tag) if o.seats_ok)
    return result(
        NoSeats(
            leg=leg,
            date=date_said(one.day, tag),
            cabin=draft.cabin,
            travelers=draft.travelers,
            cabins_with_seats=with_seats,
            other_flights=selling,
            say=SAY["no_seats_flight"],
        )
    )


def change_trip(airline: Airline, trips: TripBook) -> Tool:
    """A change to the call's draft in `trips` (the module's docstring)."""

    @tool(name=CHANGE_TRIP, description=CHANGE_DESCRIPTION)
    async def change(
        ctx: CallContext,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=_TRAVELERS)] = None,
        cabin: Annotated[Cabin | None, Field(description=_CABIN)] = None,
        one_way: Annotated[bool | None, Field(description=_ONE_WAY)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        asked: dict[Changeable, object] = {
            "travelers": travelers,
            "cabin": cabin,
            "one_way": one_way,
        }
        what = tuple(k for k, v in asked.items() if v is not None)
        if not what:
            raise ToolError(NOTHING_TO_CHANGE)
        draft = trips.get(ctx.call_id)
        if cabin is not None and draft.destination is not None:
            sold = flights(draft.origin, draft.destination)[0].cabins
            if cabin not in sold:
                offered = tuple(c for c in CABINS if c in sold)
                return result(CabinNotOffered(cabin=cabin, offered=offered))
        change = changed(draft, travelers=travelers, cabin=cabin, one_way=one_way)
        made = change.draft
        seen = view(made, tag, airline.today(), airline.flight_name)
        leg, say = _asked_next(made, change.lost)
        listed = () if leg is None else _again(list(made.shown(leg)), made, airline, tag)
        if say == "changed_relist" and not listed:
            leg, say = None, "changed"
        answer = Changed(
            changed=what, trip=seen, lost=change.lost, leg=leg, options=listed, say=SAY[say]
        )
        trips.put(ctx.call_id, made)
        return result(answer, cards.trip_card(seen, made, tag))

    return change


def _asked_next(draft: TripDraft, lost: tuple[LegKind, ...]) -> tuple[LegKind | None, str]:
    """The leg whose options a change lists again, if any, and the `say` for the change: a leg
    that lost its choice first, then a complete trip, then a missing return date, then the leg
    the caller was choosing for."""
    if lost:
        return lost[0], "changed_lost"
    if not draft.missing():
        return None, "complete"
    if not draft.one_way and draft.depart is not None and draft.return_date is None:
        return None, "changed_needs_return"
    for leg in ("outbound", "return"):
        if draft.shown(leg) and draft.chosen(leg) is None:
            return leg, "changed_relist"
    return None, "changed"
