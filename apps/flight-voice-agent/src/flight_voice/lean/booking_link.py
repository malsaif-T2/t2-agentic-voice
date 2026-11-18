"""`booking_link`, the real network's tool in place of `book_trip` (plan 011's Phase 3, the
owner's "Button on the card", D-126): registered only on the real network, read-only, with no
arguments. It reads the call's trip: a one-way trip needs its outbound chosen, a round trip both
legs. A trip still lacking something answers `incomplete` with what is `missing` (the draft's
own names: destination, depart, return_date, outbound, return).

A complete trip answers `ready`: each leg as the caller heard it (its airline, its flight, said
with the airline's name as `flight_said`, its day, its departure time and its price) and a
`note` on what to say, with the trip's review card carrying one link per leg
(flight_data/links.py's `leg_link`: the Google Flights search for that leg, filtered to its
airline), built from the trip's current legs alone, so a changed trip gets a new card. The
caller books on the airline's site from there, and the price is confirmed there.

It books nothing and never says it did: none of its results is `done`, and it declares the
booking's claims (book.py's `LEAN_CLAIMS`), so the output guard's rule A holds every booking
claim on the real network ("I've booked", «تم الحجز»): with no result that backs one, none is
ever said. The link is on the card alone, never in the result's data: the agent says the link
is ready and never reads an address aloud.
"""

from __future__ import annotations

from typing import Final

from pydantic import JsonValue
from t2_agentic_voice import CallContext, CardLink, Tool, ToolResult, tool

from flight_voice.flight_data.links import leg_link
from flight_voice.flight_data.model import Offer, Place
from flight_voice.lean.book import LEAN_CLAIMS
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LEGS, LeanDraft, LegKind
from flight_voice.lean.offer_cards import trip_card
from flight_voice.lean.picking import Picking
from flight_voice.lean.results import day_of, lean_result
from flight_voice.said import Tag, arabic, register

__all__ = ["BOOKING_LINK", "DESCRIPTION", "READY_NOTE", "booking_link", "flight_said", "trip_links"]

BOOKING_LINK: Final = "booking_link"
DESCRIPTION: Final = (
    "Give the caller the link to book the trip chosen so far on the airline's site, once every "
    "flight is chosen and the caller wants it. It takes no arguments and books nothing."
)
READY_NOTE: Final = (
    "The link to book this trip is ready. Say so in a few words, and which flight to pick when "
    "they open it: each leg's airline, its flight said as flight_said, and its departure time. "
    "Say the price is confirmed on the airline's own site. Never read the link or any address "
    "out, and never say the trip is booked: nothing is booked on this line."
)


def _route(draft: LeanDraft, leg: LegKind) -> tuple[Place, Place] | None:
    """The leg's start and end as the caller named them."""
    if draft.destination is None:
        return None
    way = (draft.origin, draft.destination)
    return way if leg == "outbound" else (way[1], way[0])


def _chosen(draft: LeanDraft) -> list[tuple[LegKind, Offer]]:
    """The trip's chosen legs, outbound first: the return only on a round trip."""
    legs = (leg for leg in LEGS if leg == "outbound" or not draft.one_way)
    return [(leg, offer) for leg in legs if (offer := draft.chosen(leg)) is not None]


def trip_links(draft: LeanDraft, tag: Tag) -> tuple[CardLink, ...]:
    """One link per chosen leg, from the trip's current legs; each labelled by its leg on a
    round trip."""
    chosen = _chosen(draft)
    named = len(chosen) > 1
    return tuple(
        leg_link(offer, tag, _route(draft, leg), leg=leg if named else None)
        for leg, offer in chosen
    )


def flight_said(offer: Offer, tag: Tag) -> str:
    """The offer's flights, each said with its marketing airline's name: "flynas 17", "Qatar
    Airways 1163 and British Airways 122", «السعودية 1020»."""
    r = register(tag)
    said = [f"{s.carrier.name(r)} {s.number}" for s in offer.segments]
    return (" و" if arabic(tag) else " and ").join(said)


def booking_link(deps: LeanDeps) -> Tool:
    """The booking link of each call's trip in `deps.trips` (the module's docstring)."""

    @tool(name=BOOKING_LINK, description=DESCRIPTION, claims=LEAN_CLAIMS)
    async def link(ctx: CallContext) -> ToolResult:
        tag: Tag = ctx.language
        draft = deps.trips.get(ctx.call_id)
        missing: list[JsonValue] = list(draft.missing())
        if missing:
            return lean_result({"status": "incomplete", "missing": missing})
        picking = Picking(draft, deps.places, tag)
        legs: list[JsonValue] = []
        for leg, offer in _chosen(draft):
            option = picking.option(offer)
            said: dict[str, JsonValue] = {
                "leg": leg,
                "airline": option.airline,
                "flight": option.flight,
                "flight_said": flight_said(offer, tag),
                "day": day_of(offer.day, tag).model_dump(mode="json"),
                "departs": option.departs,
                "price": option.price,
            }
            legs.append(said)
        card = trip_card(draft, picking.chosen_options(), tag)
        linked = None if card is None else card.model_copy(update={"links": trip_links(draft, tag)})
        return lean_result({"status": "ready", "legs": legs, "note": READY_NOTE}, linked)

    return link
