"""The way back leaves after the way out lands (the owner's calls of 2026-11-22, Qassim to
Istanbul: "lock the outbound flight first then determine the return one after it"): on the real
network, the way out is chosen first, and with it chosen a round trip's return flights are only
those leaving at least `MIN_TURNAROUND` after it lands.

The outbound lands and the return leaves at the same airport, the trip's destination, so their
local times are compared directly, as the model holds them (each offer's day, departure,
arrival and a next-day landing); no time zone is known offline, and none is needed.

- `late_enough`: whether a return offer leaves late enough after the outbound.
- `after`: a return's listing as the model reads it with the outbound chosen: its pool
  narrowed to the flights leaving late enough and listed again by listing.py's rule, so its
  options, counts and airlines are all over them; the listing itself when no outbound is
  chosen or none is left out. Every place the return's flights reach the model or the card
  reads it (picking.py's `Picking.held`): `choose_flights`' listing, card and lookup of a
  return id (one leaving too soon is `too_early`), and `find_flights`' way back with the
  outbound's pick kept (find_return.py). None left is said with `NONE_LATE_ENOUGH`.
- `kept_return`: a chosen return kept only while it leaves late enough after the chosen
  outbound; dropped otherwise (`RETURN_DROPPED`), as when another outbound is chosen.

The draft keeps each listing whole, so another outbound narrows the way back again from all its
flights. The mock keeps none of this (run F reads it as before plan 011's round 2).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from flight_voice.flight_data.model import Offer
from flight_voice.lean import listing
from flight_voice.lean.draft import LeanDraft, Listed

__all__ = [
    "MIN_TURNAROUND",
    "NONE_LATE_ENOUGH",
    "OUTBOUND_FIRST",
    "RETURN_DROPPED",
    "TOO_EARLY",
    "after",
    "kept_return",
    "late_enough",
]

MIN_TURNAROUND: Final = timedelta(hours=2)
OUTBOUND_FIRST: Final = (
    "Choose the way out first: ask which flight out they want; the way back's flights come "
    "right after it."
)
NONE_LATE_ENOUGH: Final = (
    "No flight back that day leaves after the way out lands: offer another day back."
)
TOO_EARLY: Final = (
    "That flight back leaves too soon after the way out lands (outbound_arrives): offer one "
    "of others."
)
RETURN_DROPPED: Final = (
    "The flight back chosen before leaves too soon after this way out lands, so it is dropped "
    "(lost): offer the way back again."
)


def late_enough(back: Offer, out: Offer) -> bool:
    """Whether `back` leaves at least `MIN_TURNAROUND` after `out` lands (local times at the
    same airport)."""
    return back.departs >= out.arrives + MIN_TURNAROUND


def after(listed: Listed, out: Offer | None) -> Listed:
    """The return's listing with only its flights leaving late enough after `out` (the
    module's docstring); `listed` itself when `out` is None or none is left out."""
    if out is None:
        return listed
    held = listed.pool or listed.offers
    late = tuple(o for o in held if late_enough(o, out))
    if len(late) == len(held):
        return listed
    return listed.model_copy(update={"offers": listing.listed(late), "pool": late})


def kept_return(draft: LeanDraft) -> tuple[LeanDraft, Offer | None]:
    """`draft` with its chosen return dropped when it leaves too soon after the chosen
    outbound, and the return dropped (None when kept or there is none)."""
    out, back = draft.chosen_outbound, draft.chosen_return
    if out is None or back is None or draft.one_way or late_enough(back, out):
        return draft, None
    return draft.model_copy(update={"chosen_return": None}), back
