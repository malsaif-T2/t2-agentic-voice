"""`choose_flights`, the lean agent's pick: the flights the caller chose, by the ids the model
resolved itself from the options it was given ("the most expensive", "the one at 400", "the
last one", "the morning one"). It never asks the source again: a pick is the offer as it was
listed, so the price the caller heard is the one kept. Another cabin or number of travelers
is a new search (find_flights), which keeps a pick that still has seats.

Every argument is optional: `outbound_id`, `return_id`, and `list_leg`, a leg whose flights the
caller asks to hear, listed without choosing (the way back's before the way out is chosen: a
caller may ask about it first, and is answered; a way back that could not be checked says so).
In order: nothing listed yet is `nothing_listed`; an id not among this call's latest options for
its leg is `unknown_id`, and an offer that does not seat the travelers `no_seats`, each with the
leg's other options' ids, prices and seats as data. An error writes nothing.

It returns the trip so far (`TripSoFar`): the route and the trip's kind, each with its MSA form
beside a Saudi reply's, each chosen leg as it was listed with its day, the travelers, the cabin,
`missing` (the legs still to choose, the first of them listed again in `listed`, one leg at a
time; `list_leg`'s leg in its place when given), a `note` when a leg listed has a full flight or
the way back could not be checked, and, when complete, `total` (the chosen offers' prices), the
one total the agent says. It books nothing, and its description says so: told only that it
"returns the trip", the model read a chosen trip with its total as one booked and said «حجزت
لك» before `book_trip` (f-dev-lean-4). The call's trip is written once, its last step, and
marked for the booking check. Its card: a leg still to choose in its segment, the other leg's
pick kept beside it; the whole trip and its total in the review segment once complete.

**On the real network** nothing books (D-127): the links are built in code the moment a flight
is chosen, with no tool to call (the owner, 2026-11-19). Each flight row carries its link
(offer_cards.py's `row_links`, so a pick kept beside the next leg's flights has its own), the
trip card one per chosen leg (`trip_links`), and each chosen leg says `"link": "ready"`, so the
model knows the link to book it is there. The tool declares the booking's claims (book.py's
`LEAN_CLAIMS`) and backs none (no result is `done`), so the output guard holds every booking
claim on this line.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import Field, JsonValue
from t2_agentic_voice import CallContext, Card, Tool, ToolResult, tool

from flight_voice.flight_data.model import Cabin, Place, has_seats
from flight_voice.lean.book import LEAN_CLAIMS
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LEGS, LegKind
from flight_voice.lean.find_return import RETURN_UNKNOWN
from flight_voice.lean.offer_cards import options_card, row_links, trip_card, trip_links
from flight_voice.lean.picking import Chosen, Picking
from flight_voice.lean.results import (
    LegList,
    Network,
    _Data,
    full_note,
    lean_result,
    route_said,
    trip_said,
)
from flight_voice.said import Tag

CHOOSE_FLIGHTS: Final = "choose_flights"
DESCRIPTION: Final = (
    "Choose the caller's flights by their ids from the options you were given. Pass only what "
    "the caller chose, or list_leg alone for a leg's flights the caller asks about. It returns "
    "the trip so far, the next leg's flights to choose from, and its total once every flight "
    "is chosen. It books nothing: book_trip books."
)
DESCRIPTION_REAL: Final = DESCRIPTION.replace(
    " It books nothing: book_trip books.",
    " It books nothing: the caller books on the airline's site, and each chosen flight's link "
    "to book it there is ready as soon as it is chosen (link: ready).",
)
# A chosen leg's link on the real network: on the page, ready to book it on the airline's site.
LINK_READY: Final[Literal["ready"]] = "ready"
_OUT: Final = "The id of the outbound flight the caller chose."
_BACK: Final = "The id of the return flight the caller chose."
_LIST: Final = (
    "A leg whose flights the caller asks to hear, listed without choosing one: the return's "
    "too before the outbound is chosen."
)
# What the model is told when no day's flights are listed yet (a span gives days, not flights).
NOTHING_LISTED: Final = (
    "No flights are listed to choose from: call find_flights with depart as the one day the "
    "caller wants (YYYY-MM-DD), then choose from its flights."
)


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
    listed: dict[LegKind, LegList] | None = None
    note: str | None = None


def _error(status: str, leg: LegKind, wanted: str, others: list[JsonValue]) -> ToolResult:
    return lean_result({"status": status, "leg": leg, "id": wanted, "others": others})


def choose_flights(deps: LeanDeps) -> Tool:
    """The pick over the call's trip in `deps.trips`, marked in `deps.check` (the module's
    docstring)."""

    @tool(
        name=CHOOSE_FLIGHTS,
        description=DESCRIPTION if deps.bookable else DESCRIPTION_REAL,
        claims=None if deps.network == "mock" else LEAN_CLAIMS,
    )
    async def choose(
        ctx: CallContext,
        outbound_id: Annotated[str | None, Field(max_length=40, description=_OUT)] = None,
        return_id: Annotated[str | None, Field(max_length=40, description=_BACK)] = None,
        list_leg: Annotated[LegKind | None, Field(description=_LIST)] = None,
    ) -> ToolResult:
        tag: Tag = ctx.language
        made = deps.trips.get(ctx.call_id)
        to = made.destination
        if to is None or made.listed_outbound is None:
            return lean_result({"status": "nothing_listed", "note": NOTHING_LISTED})
        picked: tuple[tuple[LegKind, str | None], ...] = (
            ("outbound", outbound_id),
            ("return", return_id),
        )
        for leg, wanted in picked:
            if wanted is None:
                continue
            picking = Picking(made, deps.places, tag)
            one = picking.find(leg, wanted)
            if one is None:
                return _error("unknown_id", leg, wanted, picking.others(leg))
            if not has_seats(one, made.travelers):
                return _error("no_seats", leg, wanted, picking.others(leg, but=wanted))
            made = made.choose(leg, one)
        if list_leg == "return" and made.return_unknown() and not (outbound_id or return_id):
            return lean_result({"status": "unknown", "note": RETURN_UNKNOWN})
        deps.trips.put(ctx.call_id, made)
        deps.check.mark(ctx.call_id, made)
        return _so_far(Picking(made, deps.places, tag), list_leg, to, deps.network)

    return choose


def _so_far(picking: Picking, asked: LegKind | None, to: Place, network: Network) -> ToolResult:
    """The trip so far to `to`, the leg `asked` about listed, and its card (the module's
    docstring)."""
    draft, tag = picking.draft, picking.tag
    route = (draft.origin, to)
    missing = tuple(leg for leg in LEGS if leg in draft.missing())
    listed = {
        leg: picking.listing(held)
        for leg in (missing[:1] if asked is None else (asked,))
        if (held := draft.listed(leg)) is not None
    }
    unknown = "return" in missing and draft.return_unknown()
    notes = (
        full_note(listed.values(), draft.travelers, draft.cabin),
        RETURN_UNKNOWN if unknown and (asked == "return" or missing[:1] == ("return",)) else None,
    )
    said, msa = route_said(route, tag)
    kind, kind_msa = trip_said(draft.one_way, tag)
    answer = TripSoFar(
        route=said,
        route_msa=msa,
        trip=kind,
        trip_msa=kind_msa,
        outbound=_linked(picking.chosen("outbound"), network),
        return_=_linked(picking.chosen("return"), network),
        travelers=draft.travelers,
        cabin=draft.cabin,
        missing=missing,
        total=None if missing else draft.total(),
        listed=listed or None,
        note=" ".join(n for n in notes if n) or None,
    )
    return lean_result(answer, _card(picking, missing, network))


def _linked(chosen: Chosen | None, network: Network) -> Chosen | None:
    """A chosen leg, its link said ready on the real network."""
    if chosen is None or network == "mock":
        return chosen
    return chosen.model_copy(update={"link": LINK_READY})


def _card(picking: Picking, missing: tuple[LegKind, ...], network: Network) -> Card | None:
    """A leg still to choose in its segment, the other's pick kept beside it; else the review,
    with a link per chosen leg on the real network."""
    draft, tag = picking.draft, picking.tag
    if not missing:
        links = () if network == "mock" else trip_links(draft, tag)
        return trip_card(draft, picking.chosen_options(), tag, links)
    leg = missing[0]
    held = draft.listed(leg)
    if held is None or draft.destination is None:
        return None
    other: LegKind = "return" if leg == "outbound" else "outbound"
    kept = picking.chosen(other)
    way = (draft.origin, draft.destination)
    way = way if leg == "outbound" else (way[1], way[0])
    options = picking.options(held)
    offers = (*held.offers, *((draft.chosen(other),) if kept is not None else ()))
    linked = row_links((o for o in offers if o is not None), tag, network)
    return options_card(leg, options, way, held.day, draft.cabin, tag, kept=kept, links=linked)
