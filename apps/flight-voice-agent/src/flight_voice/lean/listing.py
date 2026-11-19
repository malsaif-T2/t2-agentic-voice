"""Which offers a leg lists, and in what order: the same rule over every source.

**The pool** (`pool`): every nonstop; a connection joins only when the day has no nonstop, or
when it is at least `CHEAPER_BY` riyals cheaper than the cheapest nonstop and at most
`SLOWER_BY` times the fastest nonstop's time (so Saudia's 1142 connection by bus is dropped
beside flyadeal's 899 nonstop).

**The listing** (`listed`): the whole pool when it holds at most `MAX_LISTED`; else, kept in
this order until there are `MAX_LISTED`: the cheapest; each airline's cheapest, the airlines in
the order of their first departure; the earliest and the latest; the priciest (so "the most
expensive", asked of a day or of a span's day, is always one to choose: plan 011's round 2);
one for each part of the day not yet covered (its cheapest); then the cheapest of the rest.
Always in departure order, ties by id. The mock (at most four a day, one airline, all nonstop)
lists exactly its day's flights.

`by_airline` gives each airline's flights and cheapest over the pool, in the order of their
first departure, when two or more fly the day.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from flight_voice.airline.airports import Register
from flight_voice.flight_data.model import Offer
from flight_voice.lean.results import AirlineCount
from flight_voice.said import Tag, register, words

MAX_LISTED: Final = 6
CHEAPER_BY: Final = 100
SLOWER_BY: Final = 2


def _order(offer: Offer) -> tuple[object, ...]:
    return (offer.departs, offer.id)


def _cost(offer: Offer) -> tuple[object, ...]:
    return (offer.price.amount, offer.departs, offer.id)


def _dear(offer: Offer) -> tuple[object, ...]:
    return (-offer.price.amount, offer.departs, offer.id)


def pool(offers: Sequence[Offer]) -> tuple[Offer, ...]:
    """The offers a leg lists from (the module's docstring), in departure order."""
    nonstops = [o for o in offers if o.nonstop]
    if not nonstops:
        return tuple(sorted(offers, key=_order))
    cheapest = min(o.price.amount for o in nonstops)
    fastest = min(o.minutes for o in nonstops)
    kept = [
        o
        for o in offers
        if o.nonstop
        or (o.price.amount <= cheapest - CHEAPER_BY and o.minutes <= SLOWER_BY * fastest)
    ]
    return tuple(sorted(kept, key=_order))


def listed(offers: Sequence[Offer], limit: int = MAX_LISTED) -> tuple[Offer, ...]:
    """At most `limit` of `offers` (a pool), as the module's docstring keeps them, in departure
    order."""
    ordered = sorted(offers, key=_order)
    if len(ordered) <= limit:
        return tuple(ordered)
    kept: dict[str, Offer] = {}

    def keep(offer: Offer) -> None:
        if len(kept) < limit:
            kept.setdefault(offer.id, offer)

    keep(min(ordered, key=_cost))
    for code in dict.fromkeys(o.carrier.code for o in ordered):
        keep(min((o for o in ordered if o.carrier.code == code), key=_cost))
    keep(ordered[0])
    keep(ordered[-1])
    keep(min(ordered, key=_dear))
    for part in dict.fromkeys(words.part_of_day(o.departs.time()) for o in ordered):
        covered = {words.part_of_day(o.departs.time()) for o in kept.values()}
        if part not in covered:
            keep(
                min((o for o in ordered if words.part_of_day(o.departs.time()) == part), key=_cost)
            )
    for offer in sorted(ordered, key=_cost):
        keep(offer)
    return tuple(sorted(kept.values(), key=_order))


def by_airline(offers: Sequence[Offer], tag: Tag) -> tuple[AirlineCount, ...] | None:
    """Each airline's summary over `offers` (a pool): its flights, first and last departures and
    cheapest, in the order of their first departure; None when fewer than two airlines fly."""
    groups: dict[str, list[Offer]] = {}
    for offer in sorted(offers, key=_order):
        groups.setdefault(offer.carrier.code, []).append(offer)
    if len(groups) < 2:
        return None
    r = register(tag)
    return tuple(_count(held, r) for held in groups.values())


def _count(held: list[Offer], r: Register) -> AirlineCount:
    """One airline's summary over its offers, in departure order (`by_airline`)."""
    cheapest = min(held, key=lambda o: (o.price.amount, _order(o)))
    return AirlineCount(
        airline=held[0].carrier.name(r),
        flights=len(held),
        first_departs=held[0].departs.strftime("%H:%M"),
        last_departs=held[-1].departs.strftime("%H:%M"),
        cheapest=cheapest.price.amount,
        cheapest_departs=cheapest.departs.strftime("%H:%M"),
    )
