"""A leg's flights as the talker is given them: the flights a listing holds (`listable`: those
that sell the cabin, at most four, in departure order), each as an option with its fare, the
cheapest of those with seats marked (`options`), and the listing with the fare's basis said once
and the fixed `say` for it (`listing`), which asks for three aloud and how many more."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from typing import Final

from flight_voice.airline.airports import Code
from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import Cabin, Departure
from flight_voice.said import Tag, words
from flight_voice.tools.results import SAY, DateSaid, Duration, Listing, Option, date_said, said
from flight_voice.trip import LegKind

# The most options a listing holds, and the most the talker says aloud in a turn.
MAX_OPTIONS: Final = 4
SAID_ALOUD: Final = 3


def listable(found: Sequence[Departure], cabin: Cabin) -> tuple[Departure, ...]:
    """The flights of `found` a listing holds: those that sell `cabin`, `MAX_OPTIONS` at most,
    in departure order."""
    return tuple(d for d in found if cabin in d.flight.cabins)[:MAX_OPTIONS]


def options(
    found: Sequence[Departure],
    *,
    cabin: Cabin,
    travelers: int,
    tag: Tag,
    name: Callable[[int], str],
) -> tuple[Option, ...]:
    """The `listable` flights of `found` as options, numbered in departure order, each with its
    fare in `cabin`, the cheapest of those with seats marked; `name` writes a flight's number as
    a card does."""
    made: list[Option] = []
    for n, d in enumerate(listable(found, cabin), start=1):
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
    selling = [o for o in made if o.seats_ok]
    if not selling:
        return tuple(made)
    cheapest = min(selling, key=lambda o: (o.fare_sar, o.n)).n
    return tuple(o.model_copy(update={"mark": "cheapest"}) if o.n == cheapest else o for o in made)


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
) -> Listing:
    """A leg's options on `day` as the talker is given them, with the fixed `say` for them;
    an outbound listing gives the trip's return date too, said back with the departure's."""
    route_en, route_msa = said(lambda r: words.route(*route, r), tag)
    cabin_en, cabin_msa = said(lambda r: words.cabin(cabin, r), tag)
    basis, basis_msa = said(words.FARE_BASIS.__getitem__, tag)
    more = len(listed) - SAID_ALOUD if len(listed) > SAID_ALOUD else None
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
        say=SAY[("listed_more" if more else "listed") + _full(listed)],
    )


def _full(listed: tuple[Option, ...]) -> str:
    return "_full" if any(not o.seats_ok for o in listed) else ""
