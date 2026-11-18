"""`choose_flights`, the lean agent's pick and change: the flights the caller chose, by the ids
the model resolved itself from the options it was given ("the most expensive", "the one at
400", "the last one", "the morning one"), and a changed cabin or traveler count.

Every argument is optional: `outbound_id`, `return_id`, `cabin`, `travelers`, and `list_leg`,
a leg whose flights the caller asks to hear, listed without choosing (the way back's before the
way out is chosen: a caller may ask about it first, and is answered). In order:
nothing listed yet is `nothing_listed`; a cabin the route does not sell is `cabin_not_offered`;
a changed cabin or traveler count prices the chosen flights again, and a chosen flight with no
seats then is unchosen, named in `lost` by its departure time and listed again; an id not among
this call's latest options for its leg is `unknown_id`, and a flight with no seats for the
travelers in the cabin `no_seats`, each with the leg's other flights' ids, fares and seats as
data. An error writes nothing.

It returns the trip so far (`TripSoFar`): the route and the trip's kind, each with its MSA form
beside a Saudi reply's, each chosen leg with its day, times, length, nonstop and fare, the
travelers, the cabin, `missing` (the legs still to choose, the first of them listed again in
`listed`, one leg at a time: on a round trip the outbound's until it is chosen, then the
return's, which find.py gives by its day alone; `list_leg`'s leg in its place when given), a
`note` when a leg listed has a full flight, as find.py's, and, when complete, `total` (each
leg's fare times the travelers), the one total the agent says. It books nothing, and its
description says so: told only that it "returns the trip", the model read a chosen trip with its
total as one booked and said «حجزت لك» before `book_trip` (f-dev-lean-4, f01 and f30, the run's
three violations). The call's trip is written once, its last step, and marked for the booking
check. Its card: a leg still to choose in its segment, the other leg's pick kept beside it (the
return's on a round trip once the outbound is chosen); the whole trip and its total in the
review segment once complete.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import Field, JsonValue
from t2_agentic_voice import CallContext, Card, Tool, ToolResult, tool

from flight_voice.airline.airports import Code
from flight_voice.airline.bookings import Leg
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import CABINS, Cabin, flights
from flight_voice.airline.system import Airline
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.results import (
    Built,
    Day,
    LegList,
    _Data,
    day_of,
    full_note,
    lean_result,
    leg_list,
    leg_options,
    option_id,
    route_said,
    trip_said,
)
from flight_voice.said import Tag
from flight_voice.tools import cards
from flight_voice.tools.picks import departure_of
from flight_voice.tools.results import Duration
from flight_voice.tools.trip_view import chosen_option, view
from flight_voice.trip import LegKind, Shown, TripBook, TripDraft, changed

CHOOSE_FLIGHTS: Final = "choose_flights"
DESCRIPTION: Final = (
    "Choose the caller's flights by their ids from the options you were given, and change the "
    "cabin or the number of travelers. Pass only what the caller chose or changed, or list_leg "
    "alone for a leg's flights the caller asks about. It returns the trip so far, the next "
    "leg's flights to choose from, and its total once every flight is chosen. It books "
    "nothing: book_trip books."
)
_OUT: Final = "The id of the outbound flight the caller chose."
_BACK: Final = "The id of the return flight the caller chose."
_CABIN: Final = "The new cabin, only when the caller changed it."
_TRAVELERS: Final = "The new number of travelers, 1 to 9, only when the caller changed it."
_LIST: Final = (
    "A leg whose flights the caller asks to hear, listed without choosing one: the return's "
    "too before the outbound is chosen."
)
LEGS: Final[tuple[LegKind, ...]] = ("outbound", "return")


class Chosen(_Data):
    """A chosen leg: its id, its name and aircraft, its day, its local times, its length, that it
    flies nonstop and its fare per person in the cabin, so its length and stops are said from
    the data once the search that listed it is out of the model's sight."""

    id: str
    flight: str
    aircraft: str
    day: Day
    departs: str
    arrives: str
    next_day: Literal[True] | None = None
    duration: Duration
    nonstop: bool = True
    fare: int


class Lost(_Data):
    """A leg unchosen by a change, by its departure time."""

    leg: LegKind
    departs: str


class TripSoFar(_Data):
    """The trip so far (the module's docstring)."""

    status: Literal["ok"] = "ok"
    route: str
    route_msa: str | None = None
    trip: str
    trip_msa: str | None = None
    outbound: Chosen | None = None
    return_: Chosen | None = Field(default=None, alias="return")
    travelers: int
    cabin: Cabin
    missing: tuple[LegKind, ...]
    total: int | None = None
    lost: tuple[Lost, ...] | None = None
    listed: dict[LegKind, LegList] | None = None
    note: str | None = None


class _Picking:
    """One call's pick: its airline, trip and tag, and how a leg's options are built."""

    def __init__(self, airline: Airline, draft: TripDraft, tag: Tag) -> None:
        self.airline, self.draft, self.tag = airline, draft, tag

    def built(self, shown: tuple[Shown, ...]) -> Built:
        """A leg's options listed in the trip, in its cabin for its travelers now."""
        return leg_options(
            [departure_of(s) for s in shown],
            cabin=self.draft.cabin,
            travelers=self.draft.travelers,
            tag=self.tag,
            code=self.airline.code,
            name=self.airline.flight_name,
        )

    def others(self, leg: LegKind, but: str | None = None) -> list[JsonValue]:
        """The leg's listed flights but `but`: each id, fare and whether it has seats."""
        listed = self.built(self.draft.shown(leg)).data
        return [{"id": o.id, "fare": o.fare, "seats_ok": o.seats_ok} for o in listed if o.id != but]

    def find(self, leg: LegKind, wanted: str) -> Shown | None:
        code = self.airline.code
        return next(
            (s for s in self.draft.shown(leg) if option_id(code, s.flight, s.day) == wanted), None
        )

    def chosen(self, leg: LegKind) -> Chosen | None:
        leg_chosen = self.draft.chosen(leg)
        option = chosen_option(self.draft, leg, self.tag, self.airline.flight_name)
        if leg_chosen is None or option is None:
            return None
        return Chosen(
            id=option_id(self.airline.code, leg_chosen.flight, leg_chosen.day),
            flight=option.flight,
            aircraft=option.aircraft,
            day=day_of(leg_chosen.day, self.tag),
            departs=option.departs,
            arrives=option.arrives,
            next_day=option.next_day,
            duration=option.duration,
            nonstop=option.nonstop,
            fare=option.fare_sar,
        )


# What the model is told when no day's flights are listed yet (a span gives days, not flights).
NOTHING_LISTED: Final = (
    "No flights are listed to choose from: call find_flights with depart as the one day the "
    "caller wants (YYYY-MM-DD), then choose from its flights."
)


def chosen_legs(airline: Airline, draft: TripDraft, tag: Tag) -> dict[str, JsonValue]:
    """The trip's chosen legs as data, by their leg (`Chosen`), as `book_trip` gives them back."""
    picking = _Picking(airline, draft, tag)
    found = ((leg, picking.chosen(leg)) for leg in LEGS)
    return {leg: c.model_dump(mode="json") for leg, c in found if c is not None}


def _error(status: str, leg: LegKind, wanted: str, others: list[JsonValue]) -> ToolResult:
    return lean_result({"status": status, "leg": leg, "id": wanted, "others": others})


def choose_flights(airline: Airline, trips: TripBook, check: BookingCheck) -> Tool:
    """The pick and the change over the call's trip in `trips`, marked in `check` (the module's
    docstring)."""

    @tool(name=CHOOSE_FLIGHTS, description=DESCRIPTION)
    async def choose(
        ctx: CallContext,
        outbound_id: Annotated[str | None, Field(max_length=40, description=_OUT)] = None,
        return_id: Annotated[str | None, Field(max_length=40, description=_BACK)] = None,
        cabin: Annotated[Cabin | None, Field(description=_CABIN)] = None,
        travelers: Annotated[int | None, Field(ge=1, le=9, description=_TRAVELERS)] = None,
        list_leg: Annotated[LegKind | None, Field(description=_LIST)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        draft = trips.get(ctx.call_id)
        to = draft.destination
        if to is None or not draft.shown_outbound:
            return lean_result({"status": "nothing_listed", "note": NOTHING_LISTED})
        sold = flights(draft.origin, to)[0].cabins
        if cabin is not None and cabin not in sold:
            offered: list[JsonValue] = [c for c in CABINS if c in sold]
            return lean_result({"status": "cabin_not_offered", "cabin": cabin, "offered": offered})
        change = changed(draft, travelers=travelers, cabin=cabin)
        made, lost = change.draft, [(leg, draft.chosen(leg)) for leg in change.lost]
        picked: tuple[tuple[LegKind, str | None], ...] = (
            ("outbound", outbound_id),
            ("return", return_id),
        )
        for leg, wanted in picked:
            if wanted is None:
                continue
            picking = _Picking(airline, made, tag)
            one = picking.find(leg, wanted)
            if one is None:
                return _error("unknown_id", leg, wanted, picking.others(leg))
            if seats_left(departure_of(one).flight, one.day, made.cabin) < made.travelers:
                return _error("no_seats", leg, wanted, picking.others(leg, but=wanted))
            made = made.choose(leg, Leg(flight=one.flight, day=one.day))
        trips.put(ctx.call_id, made)
        check.mark(ctx.call_id, made)
        return _so_far(_Picking(airline, made, tag), lost, to, list_leg)

    return choose


def _departs(leg: Leg) -> str:
    """A chosen leg's departure time."""
    return departure_of(Shown(n=1, flight=leg.flight, day=leg.day)).departs_at.strftime("%H:%M")


def _so_far(
    picking: _Picking, lost: list[tuple[LegKind, Leg | None]], to: Code, asked: LegKind | None
) -> ToolResult:
    """The trip so far to `to`, the leg `asked` about listed, and its card (the module's
    docstring)."""
    draft, tag = picking.draft, picking.tag
    route = (draft.origin, to)
    missing = tuple(leg for leg in LEGS if leg in draft.missing())
    gone = tuple(
        Lost(leg=leg, departs=_departs(was))
        for leg, was in lost
        if was is not None and leg in missing
    )
    listed = {
        leg: leg_list(shown[0].day, picking.built(shown), tag)
        for leg in (missing[:1] if asked is None else (asked,))
        if (shown := draft.shown(leg))
    }
    said, msa = route_said(route, tag)
    kind, kind_msa = trip_said(draft.one_way, tag)
    answer = TripSoFar(
        route=said,
        route_msa=msa,
        trip=kind,
        trip_msa=kind_msa,
        outbound=picking.chosen("outbound"),
        return_=picking.chosen("return"),
        travelers=draft.travelers,
        cabin=draft.cabin,
        missing=missing,
        total=None if missing else draft.total(picking.airline.today()),
        lost=gone or None,
        listed=listed or None,
        note=full_note(listed.values(), draft.travelers, draft.cabin),
    )
    return lean_result(answer, _card(picking, missing, route))


def _card(picking: _Picking, missing: tuple[LegKind, ...], route: tuple[Code, Code]) -> Card | None:
    """A leg still to choose in its segment, the other's pick kept beside it; else the review."""
    draft, tag, airline = picking.draft, picking.tag, picking.airline
    if not missing:
        return cards.trip_card(view(draft, tag, airline.today(), airline.flight_name), draft, tag)
    leg = missing[0]
    shown = draft.shown(leg)
    if not shown:
        return None
    other: LegKind = "return" if leg == "outbound" else "outbound"
    kept = chosen_option(draft, other, tag, airline.flight_name)
    way = route if leg == "outbound" else (route[1], route[0])
    built = picking.built(shown)
    return cards.options_card(leg, built.card, way, shown[0].day, draft.cabin, tag, kept=kept)
