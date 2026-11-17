"""`change_trip`, a change to the travelers, the cabin or the trip's kind.

It changes the travelers, the cabin or one way and prices the chosen legs again: a leg whose
flight has too few seats for it now loses its choice, the result names that flight by its
departure time (`lost_departs`), and its options are listed again with their new fares, as
briefly as a listing's (their count and first and last times), a full one said as full, its card
in that leg's segment with the other leg's pick kept beside them; a complete trip goes straight
to `book_trip`, as `choose_flight`'s does. A cabin the route does not sell is
`cabin_not_offered`, and nothing changes.

The tool writes the call's draft once, as its last step.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import CallContext, Card, Tool, ToolError, ToolResult, tool

from flight_voice.airline.bookings import Leg
from flight_voice.airline.schedule import CABINS, Cabin, find_flight, flights
from flight_voice.airline.system import Airline
from flight_voice.said import Tag
from flight_voice.tools import cards
from flight_voice.tools.choose import again
from flight_voice.tools.listing import said_as, spread
from flight_voice.tools.results import SAY, CabinNotOffered, Option, _Result, result
from flight_voice.tools.trip_view import TripView, view
from flight_voice.trip import LegKind, TripBook, TripDraft, changed

CHANGE_TRIP: Final = "change_trip"
CHANGE_DESCRIPTION: Final = (
    "Change the trip the caller is planning: the number of travelers, the cabin, one way or "
    "round trip. For another day or city, call search_flights again."
)
NOTHING_TO_CHANGE: Final = (
    "Nothing was changed: pass travelers, cabin or one_way, the one the caller changed."
)
_TRAVELERS: Final = "How many people travel now, when the caller changed it."
_CABIN: Final = "The cabin the caller wants now, when they changed it."
_ONE_WAY: Final = "True for one way, false for a round trip, when the caller changed it."
Changeable = Literal["travelers", "cabin", "one_way"]
# The says that list a leg's flights again, each with its brief and full variants.
_RELISTS: Final = ("changed_relist", "changed_lost")


class Changed(_Result):
    """A trip changed: what changed, the trip priced again, the legs that lost their choice and
    the departure time of the first one's flight, and the options of the leg the caller is asked
    about next, with their new fares."""

    status: Literal["ok"] = "ok"
    changed: tuple[Changeable, ...]
    trip: TripView
    lost: tuple[LegKind, ...] = ()
    lost_departs: str | None = None
    leg: LegKind | None = None
    options: tuple[Option, ...] = ()
    count: int | None = None
    first_departs: str | None = None
    last_departs: str | None = None
    say: str


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
        listed = () if leg is None else again(list(made.shown(leg)), made, airline, tag)
        if say == "changed_relist" and not listed:
            leg, say = None, "changed"
        count, first, last = spread(listed) if listed else (None, None, None)
        if say in _RELISTS and listed:
            say += said_as(listed)
        answer = Changed(
            changed=what,
            trip=seen,
            lost=change.lost,
            lost_departs=_departs(draft.chosen(change.lost[0])) if change.lost else None,
            leg=leg,
            options=listed,
            count=count,
            first_departs=first,
            last_departs=last,
            say=SAY[say],
        )
        trips.put(ctx.call_id, made)
        return result(answer, _card(leg, listed, seen, made, tag))

    return change


def _card(
    leg: LegKind | None, listed: tuple[Option, ...], seen: TripView, made: TripDraft, tag: Tag
) -> Card | None:
    """The card of a change: the leg it lists again, in that leg's segment at the new fares,
    the other leg's pick kept beside it; else the trip."""
    day = made.depart if leg == "outbound" else made.return_date
    if leg is None or not listed or day is None or made.destination is None:
        return cards.trip_card(seen, made, tag)
    there = (made.origin, made.destination)
    route = there if leg == "outbound" else (there[1], there[0])
    kept = seen.return_flight if leg == "outbound" else seen.outbound
    return cards.options_card(leg, listed, route, day, made.cabin, tag, kept=kept)


def _departs(leg: Leg | None) -> str | None:
    """The departure time of a leg's flight, "14:40", as a listing gives it."""
    flight = None if leg is None else find_flight(leg.flight)
    return None if flight is None else flight.departs.strftime("%H:%M")


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
