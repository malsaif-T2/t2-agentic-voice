"""A round trip's way back as `find_flights` gives it (find.py), and a search for the way back
read as the trip's return (`as_return`).

**The way back** (`way_back`): its flights once the outbound's pick is kept (as
`choose_flights` lists them, so `choose_flights(return_id=...)` works), else its day alone
(`ReturnDay`): its flights come once the outbound is chosen, a pick of it kept is named in
`chosen`, and one that could not be checked is `unknown`. With the outbound kept and the
return listed, the card is the return's (`return_card`), the outbound's pick beside it, as
`choose_flights` shows it.

**A search for the way back** (`as_return`): a trip with its outbound chosen, A to B on day D,
and a new one-way search B to A on a day on or after D is the caller asking for the way back,
as the owner's call of 2026-11-19 showed: RUH to DMM on flynas chosen one way, then "make it
two ways, next Wednesday" searched DMM to RUH as a new trip, which lost the pick and the trip.
It is read as the trip's return: the search of A to B on D with that day as the return, the
same cabin and travelers, so the outbound's pick is kept and the trip becomes a round trip
(a trip already round, with its return day set, takes the new day as its return the same way).
Never while the outbound is not chosen, and never for a span.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from t2_agentic_voice import Card

from flight_voice.flight_data.model import Cabin, Place
from flight_voice.flight_data.port import Places
from flight_voice.lean.draft import LEGS, LeanDraft, LegKind
from flight_voice.lean.find_legs import Built
from flight_voice.lean.offer_cards import options_card, row_links
from flight_voice.lean.picking import Lost
from flight_voice.lean.results import Day, LegList, Network, _Data, day_of, option_of
from flight_voice.said import Tag

__all__ = [
    "RETURN_ADDED",
    "RETURN_KEPT",
    "RETURN_LISTED",
    "RETURN_UNKNOWN",
    "ReturnDay",
    "Turned",
    "as_return",
    "kept_ids",
    "lost_picks",
    "return_card",
    "way_back",
]

RETURN_LISTED: Final = (
    "Its flights come with choose_flights once the outbound is chosen, or with its list_leg "
    "when the caller asks about the way back first."
)
RETURN_KEPT: Final = "The return flight chosen before is kept; its id is in chosen."
RETURN_UNKNOWN: Final = (
    "The way back could not be checked just now; once the way out is chosen, call find_flights "
    "again with the same days to check it."
)
# A search for the way back read as the trip's return (`as_return`): the answer is the trip's
# route, which the model did not ask for, so it is told what was done.
RETURN_ADDED: Final = (
    "Read as this trip's way back: the outbound chosen before is kept (its id in chosen), the "
    "trip is now a round trip, and the return's flights are in return, to choose from."
)


class ReturnDay(_Data):
    """A round trip's return as a search gives it before the outbound is chosen: its day alone,
    or that it could not be checked (the module's docstring)."""

    status: Literal["unknown"] | None = None
    day: Day
    note: str = RETURN_LISTED


@dataclass(frozen=True)
class Turned:
    """A search for the way back, read as the trip's (`as_return`): the trip's route, its
    outbound's day, and the return's day."""

    start: Place
    end: Place
    depart: date
    back: date


def as_return(
    draft: LeanDraft, start: Place, end: Place, depart: date, back: date | None
) -> Turned | None:
    """The search from `start` to `end` on `depart`, with no return, read as the trip's way back
    (the module's docstring); None when it is not one."""
    out, to, day = draft.chosen_outbound, draft.destination, draft.depart
    if out is None or to is None or day is None or back is not None:
        return None
    if (start.code, end.code) != (to.code, draft.origin.code) or depart < day:
        return None
    return Turned(start=draft.origin, end=to, depart=day, back=depart)


def way_back(
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


def return_card(
    made: LeanDraft,
    went: Built,
    home: Built,
    route: tuple[Place, Place],
    cabin: Cabin,
    places: Places,
    tag: Tag,
    network: Network,
) -> Card | None:
    """The return's flights in its segment, the outbound's pick kept beside them, as
    `choose_flights` shows them, when the outbound's listing holds it (so every number the card
    shows is in the result's data); None when the outbound has no pick."""
    out = made.chosen_outbound
    if out is None:
        return None
    held = any(o.id == out.id for o in went.data.options)
    kept = option_of(out, tag, made.travelers, places.get) if held else None
    links = row_links((*home.listed.offers, out), tag, network)
    start, end = route
    day = home.listed.day
    options = home.data.options
    return options_card("return", options, (end, start), day, cabin, tag, kept=kept, links=links)


def kept_ids(made: LeanDraft) -> dict[LegKind, str] | None:
    """The legs whose pick the search kept, by their ids; None when it kept none."""
    kept = {leg: pick.id for leg in LEGS if (pick := made.chosen(leg)) is not None}
    return kept or None


def lost_picks(before: LeanDraft, legs: tuple[LegKind, ...]) -> tuple[Lost, ...]:
    """The picks a search dropped, by their departure times."""
    found = ((leg, before.chosen(leg)) for leg in legs)
    return tuple(Lost(leg=leg, departs=o.departs.strftime("%H:%M")) for leg, o in found if o)
