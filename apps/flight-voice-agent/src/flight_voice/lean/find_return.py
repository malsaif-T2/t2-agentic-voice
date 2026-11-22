"""A round trip's way back as `find_flights` gives it (find.py), and, on the real network, which
trip a search is (`planned`): the way back asked as its own search, or the way out changed with
the way back following it.

**The way back** (`way_back`): its flights once the outbound's pick is kept (as
`choose_flights` lists them, so `choose_flights(return_id=...)` works; on the real network only
those leaving late enough after the outbound lands, turnaround.py, with `NONE_LATE_ENOUGH` when
none does), else its day alone (`ReturnDay`): its flights come once the outbound is chosen, a
pick of it kept is named in `chosen`, and one that could not be checked is `unknown`. With the
outbound kept and the return listed, the card is the return's (`return_card`), the outbound's
pick beside it, as `choose_flights` shows it.

**A search for the way back** (`as_return`): a trip whose way out is listed (chosen or not), A
to B on day D, and a new one-way search B to A on a day on or after D is the caller asking for
the way back, as the owner's calls showed: on 2026-11-19 RUH to DMM on flynas chosen one way,
then "make it two ways, next Wednesday" searched DMM to RUH as a new trip, which lost the pick
and the trip; on 2026-11-22 the way out listed, not chosen, then the way back searched alone
replaced the trip, so the listed outbound's id was `unknown_id` three times. It is read as the
trip's return: the search of A to B on D with that day as the return, the same cabin and
travelers, the outbound's listing (its airline too) and pick kept, so the trip becomes a round
trip, both legs searched (a trip already round, with its return day set, takes the new day as
its return the same way). Its flights are listed: with the outbound chosen, those leaving
late enough after it lands (`RETURN_ADDED`); else every flight of the day, since the caller
asked about them (`RETURN_ASKED`: the way out is chosen first, or both in one call, the way
back checked against it; replayed on 2026-11-22, given the return's day alone the model had
no ids for "flynas both ways"). Never for a span, and never for a day before D (a new trip).

**The way out changed** (`planned`): on a round trip, a search for the way out that is not a
search back and gives no return day keeps the trip round: its return day is kept when it is on
or after the new day out, the way back searched from the new destination (`BACK_KEPT`); one
before the new day out leaves the trip round with no return day, asked again (`BACK_BEFORE`,
and `NO_BACK_DAY` while it stays unset). `one_way` makes the trip one way. The picks follow
draft.py's `searched`, and turnaround.py's check for the return's.
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
from flight_voice.lean.picking import Lost, Picking
from flight_voice.lean.results import Day, LegList, Network, _Data, day_of, option_of
from flight_voice.lean.turnaround import NONE_LATE_ENOUGH
from flight_voice.said import Tag, register

__all__ = [
    "BACK_BEFORE",
    "BACK_KEPT",
    "NO_BACK_DAY",
    "RETURN_ADDED",
    "RETURN_ASKED",
    "RETURN_KEPT",
    "RETURN_LISTED",
    "RETURN_UNKNOWN",
    "Planned",
    "ReturnDay",
    "as_return",
    "kept_ids",
    "lost_picks",
    "planned",
    "return_card",
    "trip_notes",
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
RETURN_ASKED: Final = (
    "Read as this trip's way back on {day}: its flights are in return. The way out is not "
    "chosen yet (its flights are in outbound, their ids as before): choose it first, or both "
    "in one call (outbound_id with return_id) when the caller picked both."
)
BACK_KEPT: Final = "The way back stays on {day}, now from {city}."
BACK_BEFORE: Final = (
    "The way back on {day} is before the new day out: ask which day they come back."
)
NO_BACK_DAY: Final = "The way back's day is not set yet: ask which day they come back."


class ReturnDay(_Data):
    """A round trip's return as a search gives it before the outbound is chosen: its day alone,
    or that it could not be checked (the module's docstring)."""

    status: Literal["unknown"] | None = None
    day: Day
    note: str = RETURN_LISTED


@dataclass(frozen=True)
class Planned:
    """The search a call makes on the real network (`planned`): its route and days; `turned`
    when it is the trip's way back read as its return, the outbound's listing narrowed to
    `airline`; `round_trip` when the trip stays round with no return day; and `kept`, the
    trip's return day kept or set aside, for its note."""

    start: Place
    end: Place
    depart: date
    back: date | None
    turned: bool = False
    airline: str | None = None
    round_trip: bool = False
    kept: date | None = None


def as_return(
    draft: LeanDraft, start: Place, end: Place, depart: date, back: date | None
) -> Planned | None:
    """The search from `start` to `end` on `depart`, with no return, read as the trip's way back
    (the module's docstring); None when it is not one."""
    to, day, out = draft.destination, draft.depart, draft.listed_outbound
    if to is None or day is None or out is None or back is not None:
        return None
    if (start.code, end.code) != (to.code, draft.origin.code) or depart < day:
        return None
    return Planned(draft.origin, to, day, depart, turned=True, airline=out.airline)


def planned(
    draft: LeanDraft, start: Place, end: Place, depart: date, back: date | None, *, one_way: bool
) -> Planned:
    """Which trip the search from `start` to `end` is, over the call's `draft` (the module's
    docstring): the trip's way back, whatever `one_way` says (replayed on 2026-11-22, the model
    passed it for the way back's own search, which made the way back a new trip); else one way
    when `one_way`, the way out with the way back following it, or the search as asked."""
    turned = as_return(draft, start, end, depart, back)
    if turned is not None:
        return turned
    if one_way:
        return Planned(start, end, depart, None)
    to = draft.destination
    if back is not None or draft.one_way or to is None:
        return Planned(start, end, depart, back)
    if (start.code, end.code) == (to.code, draft.origin.code):  # a search back, before D
        return Planned(start, end, depart, None)
    kept = draft.return_date
    if kept is not None and kept >= depart:
        return Planned(start, end, depart, kept, kept=kept)
    return Planned(start, end, depart, None, round_trip=True, kept=kept)


def way_back(
    made: LeanDraft,
    back: date | None,
    home: Built | None,
    tag: Tag,
    places: Places,
    *,
    turned: bool = False,
    real: bool = False,
) -> tuple[LegList | ReturnDay | None, Built | None]:
    """A round trip's return as the search gives it, and its flights as listed when it gives
    them (for its card): its flights when the outbound's pick is kept (on the `real` network
    those leaving late enough after it lands), or every flight of the day when the search was
    the trip's way back (`turned`), else its day alone, saying so when the return's pick is
    kept or the return could not be checked (the module's docstring)."""
    if back is None:
        return None, None
    if home is None:
        return ReturnDay(status="unknown", day=day_of(back, tag), note=RETURN_UNKNOWN), None
    if made.chosen_outbound is not None:
        shown = _later(made, home, tag, places) if real else home
        return shown.data, shown
    if turned:  # the caller asked about the way back: its flights, the way out chosen first
        return home.data, home
    note = RETURN_KEPT if made.chosen_return is not None else RETURN_LISTED
    return ReturnDay(day=day_of(back, tag), note=note), None


def _later(made: LeanDraft, home: Built, tag: Tag, places: Places) -> Built:
    """The return's flights leaving late enough after the chosen outbound lands, as the model
    and the card read them; `home` itself when none is left out."""
    picking = Picking(made, places, tag, turnaround=True)
    held = picking.held("return")
    if held is None or held == home.listed:
        return home
    return Built(picking.listing(held), held)


def trip_notes(
    plan: Planned | None,
    made: LeanDraft,
    shown: LegList | ReturnDay | None,
    end: Place,
    tag: Tag,
) -> tuple[str | None, ...]:
    """The notes on the trip a real search made (`plan`): the way back read as the return,
    kept, or its day asked again; and no flight back leaving late enough (the module's
    docstring)."""
    if plan is None:
        return ()
    none = isinstance(shown, LegList) and not shown.options and made.chosen_outbound is not None
    return (_plan_note(plan, made, end, tag), NONE_LATE_ENOUGH if none else None)


def _plan_note(plan: Planned, made: LeanDraft, end: Place, tag: Tag) -> str | None:
    if plan.turned:
        if made.chosen_outbound is not None:
            return RETURN_ADDED
        return RETURN_ASKED.format(day=plan.back.isoformat()) if plan.back else None
    if plan.kept is None:
        return NO_BACK_DAY if plan.round_trip else None
    if plan.back == plan.kept:
        return BACK_KEPT.format(day=plan.kept.isoformat(), city=end.city(register(tag)))
    return BACK_BEFORE.format(day=plan.kept.isoformat())


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
    shows is in the result's data); with no pick yet, the return's flights alone."""
    out = made.chosen_outbound
    held = out is not None and any(o.id == out.id for o in went.data.options)
    kept = option_of(out, tag, made.travelers, places.get) if out and held else None
    links = row_links((*home.listed.offers, *((out,) if out else ())), tag, network)
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
