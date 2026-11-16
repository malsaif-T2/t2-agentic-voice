"""The trip a call is planning, kept in code (`TripDraft`), one per call (`TripBook`).

The talker's history may lose old tool results, and a model reads "the second one" wrong, so
the route, the dates, the travelers, the cabin, the options last listed for each leg (in the
order said) and the flight chosen for each leg live here, and the tools resolve a pick against
them. A draft is frozen: each change makes a new one, and a tool puts it in the book as its last
step, in one assignment, so a tool cancelled by a barge-in leaves the draft as it was or wholly
changed.

The defaults are the traveler's: from their home airport, a round trip, one traveler, their
preferred cabin. A changed date clears that leg's choice; a changed cabin or traveler count keeps
a leg's choice only while its flight has seats for every traveler in the new cabin (`changed`).
The book keeps at most 64 calls, the oldest dropped past it, and drops a call's draft when the
call ends (`call_ended`, an observer of `CallEnded`).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice.events import CallEnded

from flight_voice.airline.airports import HOME, Code
from flight_voice.airline.bookings import BookingRefused, Leg, priced
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import Cabin, find_flight

LegKind = Literal["outbound", "return"]
Missing = Literal["destination", "depart", "return_date", "outbound", "return"]
MAX_CALLS: Final = 64


class Shown(BaseModel):
    """An option listed to the caller: its place in the list as said, its flight and day."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int = Field(ge=1, le=4)
    flight: int
    day: date


class TripDraft(BaseModel):
    """The trip planned so far (the module's docstring)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Code = HOME
    destination: Code | None = None
    depart: date | None = None
    return_date: date | None = None
    one_way: bool = False
    travelers: int = Field(default=1, ge=1, le=9)
    cabin: Cabin = "economy"
    shown_outbound: tuple[Shown, ...] = ()
    shown_return: tuple[Shown, ...] = ()
    chosen_outbound: Leg | None = None
    chosen_return: Leg | None = None

    def shown(self, leg: LegKind) -> tuple[Shown, ...]:
        """The options last listed for `leg`."""
        return self.shown_outbound if leg == "outbound" else self.shown_return

    def chosen(self, leg: LegKind) -> Leg | None:
        """The flight chosen for `leg`, or `None`."""
        return self.chosen_outbound if leg == "outbound" else self.chosen_return

    def missing(self) -> tuple[Missing, ...]:
        """What the trip still lacks before it can be booked, in the order it is asked."""
        needs: list[Missing] = []
        if self.destination is None:
            needs.append("destination")
        if self.depart is None:
            needs.append("depart")
        if not self.one_way and self.return_date is None:
            needs.append("return_date")
        if self.chosen_outbound is None:
            needs.append("outbound")
        if not self.one_way and self.chosen_return is None:
            needs.append("return")
        return tuple(needs)

    def legs(self) -> tuple[Leg, ...]:
        """The chosen legs, outbound first: the return only on a round trip."""
        chosen = (self.chosen_outbound, None if self.one_way else self.chosen_return)
        return tuple(leg for leg in chosen if leg is not None)

    def total(self, today: date) -> int | None:
        """The trip's total, every leg chosen and priced now, or `None` while a leg is missing
        or a chosen one can no longer be sold as it is."""
        if self.missing():
            return None
        try:
            return priced(self.legs(), self.cabin, self.travelers, today)
        except BookingRefused:
            return None

    def listed(self, leg: LegKind, options: tuple[Shown, ...]) -> TripDraft:
        """This draft with `options` the last listed for `leg`."""
        field = "shown_outbound" if leg == "outbound" else "shown_return"
        return self.model_copy(update={field: options})

    def choose(self, leg: LegKind, choice: Leg) -> TripDraft:
        """This draft with `choice` the flight of `leg`."""
        field = "chosen_outbound" if leg == "outbound" else "chosen_return"
        return self.model_copy(update={field: choice})

    def searched(
        self,
        *,
        origin: Code,
        destination: Code,
        depart: date,
        return_date: date | None,
        one_way: bool,
        travelers: int,
        cabin: Cabin,
    ) -> TripDraft:
        """This draft with a search's route, dates, travelers and cabin: a leg keeps its choice
        and its options only while its route and day are the same."""
        same_route = (origin, destination) == (self.origin, self.destination)
        keep_out = same_route and depart == self.depart
        keep_back = same_route and not one_way and return_date == self.return_date
        draft = TripDraft(
            origin=origin,
            destination=destination,
            depart=depart,
            return_date=None if one_way else return_date,
            one_way=one_way,
            travelers=self.travelers,
            cabin=self.cabin,
            shown_outbound=self.shown_outbound if keep_out else (),
            shown_return=self.shown_return if keep_back else (),
            chosen_outbound=self.chosen_outbound if keep_out else None,
            chosen_return=self.chosen_return if keep_back else None,
        )
        return changed(draft, travelers=travelers, cabin=cabin).draft


@dataclass(frozen=True)
class Change:
    """A changed draft, and the legs whose choice it lost for too few seats."""

    draft: TripDraft
    lost: tuple[LegKind, ...] = ()


def changed(
    draft: TripDraft,
    *,
    travelers: int | None = None,
    cabin: Cabin | None = None,
    one_way: bool | None = None,
) -> Change:
    """`draft` with the travelers, the cabin or one way changed (each kept when `None`): one way
    drops the return; a leg whose flight lacks seats for every traveler in the cabin, or does not
    sell it, loses its choice, and is named in `lost`."""
    update: dict[str, object] = {}
    if travelers is not None:
        update["travelers"] = travelers
    if cabin is not None:
        update["cabin"] = cabin
    if one_way is not None:
        update["one_way"] = one_way
        if one_way:
            update |= {"return_date": None, "shown_return": (), "chosen_return": None}
    made = draft.model_copy(update=update)
    made = TripDraft.model_validate(made.model_dump())
    lost: list[LegKind] = []
    for leg in ("outbound", "return"):
        chosen = made.chosen(leg)
        if chosen is not None and not _seats_for(chosen, made.cabin, made.travelers):
            made = made.model_copy(update={f"chosen_{leg}": None})
            lost.append(leg)
    return Change(made, tuple(lost))


def _seats_for(leg: Leg, cabin: Cabin, travelers: int) -> bool:
    flight = find_flight(leg.flight)
    return flight is not None and seats_left(flight, leg.day, cabin) >= travelers


class TripBook:
    """One draft per call, by its call ID, at most `max_calls` of them (the oldest dropped past
    it); a call with none yet starts from `start()`."""

    def __init__(
        self, *, start: Callable[[], TripDraft] = TripDraft, max_calls: int = MAX_CALLS
    ) -> None:
        self._start = start
        self._max = max_calls
        self._drafts: OrderedDict[str, TripDraft] = OrderedDict()

    def __len__(self) -> int:
        return len(self._drafts)

    def get(self, call_id: str) -> TripDraft:
        """The call's draft, or a new one when it has none (which is not kept until put)."""
        draft = self._drafts.get(call_id)
        return draft if draft is not None else self._start()

    def put(self, call_id: str, draft: TripDraft) -> None:
        """Make `draft` the call's, in one assignment; the oldest call is dropped past the cap."""
        self._drafts[call_id] = draft
        self._drafts.move_to_end(call_id)
        while len(self._drafts) > self._max:
            self._drafts.popitem(last=False)

    def drop(self, call_id: str) -> None:
        """Forget the call's draft."""
        self._drafts.pop(call_id, None)

    async def call_ended(self, event: CallEnded) -> None:
        """Drop the ended call's draft: `runtime.on(CallEnded)(book.call_ended)`."""
        self.drop(event.call_id)
