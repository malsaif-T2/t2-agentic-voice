"""The trip a lean call is planning (`LeanDraft`), one per call (`LeanBook`), holding the offers
as the caller heard them.

The scripted agent's draft (trip.py) keeps a flight's number and works its fare out again from
the mock's timetable; a live source's price changes and cannot be worked out again, so this
draft keeps each leg's listing (`Listed`: its day, the offers said in that order, the pool they
were listed from, and the airline the search was narrowed to) and each pick as the `Offer`
itself. Its `total` is the chosen offers' prices summed, which is what the caller was told.

A draft is frozen: each change makes a new one, and a tool puts it in the book as its last
step, in one assignment, so a tool cancelled by a barge-in leaves the draft as it was or wholly
changed. A search (`searched`) keeps a leg's pick only while its route and day are the same and
the new answer still holds an offer of that id with seats for the travelers: the new offer is
kept (its new price), so the total equals what was just said; a pick dropped so is named in
`lost`. A search with no return day makes the trip one way, unless it says the trip stays round
(`one_way` false: the real network's way out changed while its way back's day is asked again,
find_return.py), when `missing` holds the return's day. On the real network a kept return pick
must also leave late enough after the outbound's (turnaround.py). The book keeps at most 64
calls and drops a call's draft when the call ends.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice.events import CallEnded

from flight_voice.flight_data.model import Cabin, Offer, Place, has_seats
from flight_voice.flight_data.queries import DayOffers

__all__ = [
    "LEGS",
    "MAX_CALLS",
    "LeanBook",
    "LeanChange",
    "LeanDraft",
    "LegKind",
    "Listed",
    "Missing",
    "searched",
]

LegKind = Literal["outbound", "return"]
Missing = Literal["destination", "depart", "return_date", "outbound", "return"]
LEGS: Final[tuple[LegKind, ...]] = ("outbound", "return")
MAX_CALLS: Final = 64


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Listed(_Frozen):
    """A leg's flights as last listed: its day, the offers said (in that order), the pool they
    were listed from (for the counts said with them), and the airline it was narrowed to."""

    day: date
    offers: tuple[Offer, ...]
    pool: tuple[Offer, ...] = ()
    airline: str | None = None


class LeanDraft(_Frozen):
    """The trip planned so far (the module's docstring)."""

    origin: Place
    destination: Place | None = None
    depart: date | None = None
    return_date: date | None = None
    one_way: bool = False
    travelers: int = Field(default=1, ge=1, le=9)
    cabin: Cabin = "economy"
    listed_outbound: Listed | None = None
    listed_return: Listed | None = None
    chosen_outbound: Offer | None = None
    chosen_return: Offer | None = None

    def listed(self, leg: LegKind) -> Listed | None:
        """The flights last listed for `leg`."""
        return self.listed_outbound if leg == "outbound" else self.listed_return

    def chosen(self, leg: LegKind) -> Offer | None:
        """The offer chosen for `leg`, or None."""
        return self.chosen_outbound if leg == "outbound" else self.chosen_return

    def missing(self) -> tuple[Missing, ...]:
        """What the trip still lacks, in the order it is asked."""
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

    def legs(self) -> tuple[Offer, ...]:
        """The chosen offers, outbound first: the return only on a round trip."""
        chosen = (self.chosen_outbound, None if self.one_way else self.chosen_return)
        return tuple(o for o in chosen if o is not None)

    def return_unknown(self) -> bool:
        """Whether the way back was asked for but could not be checked: a round trip with its
        day set and nothing listed for it."""
        return not self.one_way and self.return_date is not None and self.listed_return is None

    def total(self) -> int | None:
        """The chosen offers' prices summed, once nothing is missing; else None."""
        if self.missing():
            return None
        return sum(o.price.amount for o in self.legs())

    def with_listing(self, leg: LegKind, listed: Listed | None) -> LeanDraft:
        """This draft with `listed` the last listed for `leg`."""
        return self.model_copy(update={f"listed_{leg}": listed})

    def choose(self, leg: LegKind, offer: Offer) -> LeanDraft:
        """This draft with `offer` chosen for `leg`."""
        return self.model_copy(update={f"chosen_{leg}": offer})


@dataclass(frozen=True)
class LeanChange:
    """A searched draft, and the legs whose pick it dropped."""

    draft: LeanDraft
    lost: tuple[LegKind, ...] = ()


def _kept(
    pick: Offer | None, answer: DayOffers | None, travelers: int
) -> tuple[Offer | None, bool]:
    """The pick as the new answer holds it (its new snapshot) and whether it was dropped."""
    if pick is None:
        return None, False
    if answer is None:
        return None, True
    again = next((o for o in answer.offers if o.id == pick.id), None)
    if again is None or not has_seats(again, travelers):
        return None, True
    return again, False


def searched(
    draft: LeanDraft,
    *,
    origin: Place,
    destination: Place,
    depart: date,
    return_date: date | None,
    travelers: int,
    cabin: Cabin,
    out: tuple[DayOffers, Listed],
    back: tuple[DayOffers, Listed] | None,
    one_way: bool | None = None,
) -> LeanChange:
    """`draft` with a search's route, days, travelers and cabin, and each leg's answer and
    listing (`back` None for one way, or for a way back that could not be checked): the
    module's docstring. A way back not checked keeps its pick only when nothing about that leg
    changed. The trip is one way when it has no return day, unless `one_way` says otherwise."""
    if one_way is None:
        one_way = return_date is None
    same_route = (origin.code, destination.code) == (
        draft.origin.code,
        None if draft.destination is None else draft.destination.code,
    )
    party_same = (travelers, cabin) == (draft.travelers, draft.cabin)
    lost: list[LegKind] = []
    picked_out: Offer | None = None
    if same_route and depart == draft.depart:
        picked_out, dropped = _kept(draft.chosen_outbound, out[0], travelers)
        lost += ["outbound"] if dropped else []
    picked_back: Offer | None = None
    same_back = not one_way and return_date is not None and return_date == draft.return_date
    if same_route and same_back:
        if back is None and party_same:
            picked_back = draft.chosen_return
        else:
            answer = None if back is None else back[0]
            picked_back, dropped = _kept(draft.chosen_return, answer, travelers)
            lost += ["return"] if dropped else []
    made = LeanDraft(
        origin=origin,
        destination=destination,
        depart=depart,
        return_date=return_date,
        one_way=one_way,
        travelers=travelers,
        cabin=cabin,
        listed_outbound=out[1],
        listed_return=None if back is None else back[1],
        chosen_outbound=picked_out,
        chosen_return=picked_back,
    )
    return LeanChange(made, tuple(lost))


class LeanBook:
    """One draft per call, by its call ID, at most `max_calls` of them (the oldest dropped past
    it); a call with none yet starts from `home`."""

    def __init__(self, home: Place, *, max_calls: int = MAX_CALLS) -> None:
        self.home = home
        self._max = max_calls
        self._drafts: OrderedDict[str, LeanDraft] = OrderedDict()

    def __len__(self) -> int:
        return len(self._drafts)

    def get(self, call_id: str) -> LeanDraft:
        """The call's draft, or a new one from `home` (not kept until put)."""
        draft = self._drafts.get(call_id)
        return draft if draft is not None else LeanDraft(origin=self.home)

    def put(self, call_id: str, draft: LeanDraft) -> None:
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
