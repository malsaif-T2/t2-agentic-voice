"""A leg's flights as the talker is given them: the flights a listing holds (`listable`: those
that sell the cabin, at most four, in the order said), each as an option with its fare, the
cheapest of those with seats marked (`options`), and the listing with the fare's basis said once
and the fixed `say` for it (`listing`), which asks for options 1 to 3 aloud and the one more by
its part of the day, never its time or its fare. A listing after one of another day (`again`)
asks for its day first and the basis not said again.

The order said is the numbers' order, so "the third one" is the third the caller heard: the
three said, in departure order, then the one left out. They are the first three to leave, unless
the cheapest with a seat for every traveler leaves last: then it is said, and the one left out
is, of the first three, a full one first, then the dearest, then the last to leave."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from typing import Final

from flight_voice.airline.airports import Code
from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import Cabin, Departure
from flight_voice.said import Tag, words
from flight_voice.tools.picks import departure_of
from flight_voice.tools.results import SAY, DateSaid, Duration, Listing, Option, date_said, said
from flight_voice.trip import LegKind, Shown

# The most options a listing holds, and the most the talker says aloud in a turn.
MAX_OPTIONS: Final = 4
SAID_ALOUD: Final = 3


def listable(found: Sequence[Departure], cabin: Cabin, travelers: int) -> tuple[Departure, ...]:
    """The flights of `found` (in departure order) a listing holds: those that sell `cabin`,
    `MAX_OPTIONS` at most, in the order said for `travelers` (the module's docstring)."""
    kept = tuple(d for d in found if cabin in d.flight.cabins)[:MAX_OPTIONS]
    if len(kept) <= SAID_ALOUD:
        return kept
    cost = [fare(d, cabin) or 0 for d in kept]  # every kept flight sells the cabin
    seated = [i for i, d in enumerate(kept) if seats_left(d.flight, d.day, cabin) >= travelers]
    cheapest = min(seated, key=lambda i: (cost[i], i)) if seated else 0
    if cheapest < SAID_ALOUD:
        return kept
    full = [i not in seated for i in range(len(kept))]
    out = max(range(SAID_ALOUD), key=lambda i: (full[i], cost[i], i))
    said_aloud = [d for i, d in enumerate(kept[:SAID_ALOUD]) if i != out] + [kept[cheapest]]
    rest = [kept[out]] + [d for i, d in enumerate(kept) if i >= SAID_ALOUD and i != cheapest]
    return (*said_aloud, *rest)


def options(
    found: Sequence[Departure],
    *,
    cabin: Cabin,
    travelers: int,
    tag: Tag,
    name: Callable[[int], str],
) -> tuple[Option, ...]:
    """The `listable` flights of `found` as options, numbered in the order said, each with its
    fare in `cabin`, the cheapest of those with seats marked; `name` writes a flight's number as
    a card does."""
    made: list[Option] = []
    for n, d in enumerate(listable(found, cabin, travelers), start=1):
        price = fare(d, cabin) or 0  # `listable` keeps the flights that sell the cabin
        minutes = int(d.flight.duration.total_seconds()) // 60
        part, part_msa = said(partial(words.part_said, d.flight.departs), tag)
        made.append(
            Option(
                n=n,
                flight=name(d.flight.number),
                aircraft=d.flight.aircraft,
                departs=d.departs_at.strftime("%H:%M"),
                arrives=d.arrives_at.strftime("%H:%M"),
                next_day=True if d.next_day else None,
                duration=Duration(hours=minutes // 60, minutes=minutes % 60),
                part_of_day_said=part,
                part_of_day_said_msa=part_msa,
                fare_sar=price,
                seats_ok=seats_left(d.flight, d.day, cabin) >= travelers,
            )
        )
    return marked(made)


def marked(made: Sequence[Option]) -> tuple[Option, ...]:
    """`made` with the cheapest option that has seats marked (the first listed of two as
    cheap), and no other; none marked when none has seats."""
    selling = [o for o in made if o.seats_ok]
    cheapest = min(selling, key=lambda o: (o.fare_sar, o.n)).n if selling else None
    return tuple(
        o.model_copy(update={"mark": "cheapest" if o.n == cheapest else None}) for o in made
    )


def listing(
    leg: LegKind,
    route: tuple[Code, Code],
    day: date,
    listed: tuple[Option, ...],
    *,
    travelers: int,
    cabin: Cabin,
    tag: Tag,
    assumed: bool = False,
    return_date: DateSaid | None = None,
    again: bool = False,
) -> Listing:
    """A leg's options on `day` as the talker is given them, with the fixed `say` for them (a
    `relisted` one when `again`, the caller having heard another day's; else an outbound one
    said from its day, a return one with its own say); an outbound listing gives the trip's
    return date too, said back with the departure's."""
    route_en, route_msa = said(lambda r: words.route(*route, r), tag)
    cabin_en, cabin_msa = said(lambda r: words.cabin(cabin, r), tag)
    basis, basis_msa = said(words.FARE_BASIS.__getitem__, tag)
    more = len(listed) - SAID_ALOUD if len(listed) > SAID_ALOUD else None
    first = "return_listed" if leg == "return" else "listed"
    return Listing(
        leg=leg,
        route_said=route_en,
        route_said_msa=route_msa,
        date=date_said(day, tag, assumed=assumed),
        return_date=return_date,
        options=listed,
        more=more,
        travelers=travelers,
        cabin=cabin,
        cabin_said=cabin_en,
        cabin_said_msa=cabin_msa,
        fare_basis_said=basis,
        fare_basis_said_msa=basis_msa,
        say=SAY[("relisted" if again else first) + ("_more" if more else "") + _full(listed)],
    )


def _full(listed: tuple[Option, ...]) -> str:
    return "_full" if any(not o.seats_ok for o in listed) else ""


def listed_again(
    shown: Sequence[Shown],
    *,
    cabin: Cabin,
    travelers: int,
    tag: Tag,
    name: Callable[[int], str],
    mark: bool = True,
) -> tuple[Option, ...]:
    """Options already listed, priced again in `cabin` for `travelers`, each keeping its number
    in the list as said, the cheapest with seats marked unless `mark` is false. One whose
    flight does not sell the cabin is left out."""
    made: list[Option] = []
    for s in shown:
        priced = options([departure_of(s)], cabin=cabin, travelers=travelers, tag=tag, name=name)
        made += [o.model_copy(update={"n": s.n, "mark": None}) for o in priced]
    return marked(made) if mark else tuple(made)
