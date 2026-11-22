"""A lean call's picks as the model reads them, over the offers its draft holds: a chosen leg
(`Chosen`: the option as it was listed, with its day), a pick a search or another outbound
dropped (`Lost`, by its departure time), and a leg's listing read again from the draft
(`listing`), with the counts of the pool it was listed from. On the real network
(`turnaround`), with the outbound chosen, the return's flights are only those leaving late
enough after it lands (turnaround.py's `after`): its listing, the ids it takes and the others
said beside a refusal; a return id listed but leaving too soon is `too_early`. Nothing here
asks the source again."""

from __future__ import annotations

from typing import Literal

from pydantic import JsonValue

from flight_voice.flight_data.model import Offer
from flight_voice.flight_data.port import Places
from flight_voice.lean.draft import LEGS, LeanDraft, LegKind, Listed
from flight_voice.lean.listing import by_airline
from flight_voice.lean.results import Day, LeanOption, LegList, _Data, day_of, leg_list, option_of
from flight_voice.lean.turnaround import after
from flight_voice.said import Tag

__all__ = ["Chosen", "Lost", "Picking", "chosen_legs"]


class Chosen(LeanOption):
    """A chosen leg: its option, and its day, so its length and stops are said from the data
    once the search that listed it is out of the model's sight; on the real network, that its
    link to book it is ready (`link`, choose.py)."""

    day: Day
    link: Literal["ready"] | None = None


class Lost(_Data):
    """A leg whose pick a search dropped, by its departure time."""

    leg: LegKind
    departs: str


class Picking:
    """One call's draft read for the model: its places, travelers and tag; with `turnaround`
    (the real network), the return's flights as the chosen outbound leaves them (the module's
    docstring)."""

    def __init__(
        self, draft: LeanDraft, places: Places, tag: Tag, *, turnaround: bool = False
    ) -> None:
        self.draft, self.places, self.tag = draft, places, tag
        self.turnaround = turnaround

    def held(self, leg: LegKind) -> Listed | None:
        """The flights last listed for `leg` as the model reads them: with `turnaround` and the
        outbound chosen, the return's leaving late enough after it lands."""
        listed = self.draft.listed(leg)
        if listed is None or leg == "outbound" or not self.turnaround:
            return listed
        return after(listed, self.draft.chosen_outbound)

    def option(self, offer: Offer) -> LeanOption:
        return option_of(offer, self.tag, self.draft.travelers, self.places.get)

    def options(self, listed: Listed) -> tuple[LeanOption, ...]:
        return tuple(self.option(o) for o in listed.offers)

    def listing(self, listed: Listed) -> LegList:
        """A leg's listing as the search gave it: its options, and the pool's counts."""
        held = listed.pool or listed.offers
        return leg_list(
            listed.day,
            self.options(listed),
            self.tag,
            count=len(held),
            airlines=by_airline(held, self.tag),
        )

    def others(self, leg: LegKind, but: str | None = None) -> list[JsonValue]:
        """The leg's listed offers but `but`: each id, price and whether it seats everyone."""
        listed = self.held(leg)
        found: list[JsonValue] = []
        for o in () if listed is None else self.options(listed):
            if o.id != but:
                other: dict[str, JsonValue] = {"id": o.id, "price": o.price}
                found.append(other if o.seats_ok is None else other | {"seats_ok": o.seats_ok})
        return found

    def find(self, leg: LegKind, wanted: str) -> Offer | None:
        """The leg's listed offer of id `wanted` (one of the pool it was listed from too, which
        the day's airline summary names by id), or its pick by that id."""
        listed = self.held(leg)
        offers = () if listed is None else (*listed.offers, *listed.pool)
        chosen = self.draft.chosen(leg)
        return next((o for o in (*offers, *([chosen] if chosen else [])) if o.id == wanted), None)

    def too_early(self, leg: LegKind, wanted: str) -> bool:
        """Whether `wanted`, not found by `find`, is a return listed that leaves too soon after
        the chosen outbound lands."""
        if not self.turnaround or leg == "outbound":
            return False
        return Picking(self.draft, self.places, self.tag).find(leg, wanted) is not None

    def chosen(self, leg: LegKind) -> Chosen | None:
        """The leg's pick as the model reads it, or None."""
        offer = self.draft.chosen(leg)
        if offer is None or (leg == "return" and self.draft.one_way):
            return None
        option = self.option(offer)
        return Chosen(**option.model_dump(), day=day_of(offer.day, self.tag))

    def chosen_options(self) -> dict[LegKind, LeanOption]:
        """Every leg's pick as an option, by its leg."""
        return {leg: c for leg in LEGS if (c := self.chosen(leg)) is not None}


def chosen_legs(draft: LeanDraft, places: Places, tag: Tag) -> dict[str, JsonValue]:
    """The trip's chosen legs as data, by their leg (`Chosen`), as `book_trip` gives them back."""
    picking = Picking(draft, places, tag)
    return {
        leg: c.model_dump(mode="json", exclude_none=True)
        for leg, c in picking.chosen_options().items()
    }
