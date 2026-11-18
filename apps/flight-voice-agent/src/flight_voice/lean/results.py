"""What the lean tools give the model: plain data, never a script of what to say (D-113).

A flight option (`LeanOption`) is an offer the source gave, by its id (its flights' codes and
its day: "T2401-2026-11-19", "SV3079+SV8607-2026-11-19"): its airline, its flights and aircraft
(said only when asked; the cards show them, so every number a card shows is in the data), its
local times at each end, its length, its stops with where and how long each wait is (`via`), a
road leg by bus, the carrier that flies it when another does, its price for all the travelers
on that leg, whether it seats every traveler (only when the source counts seats: the mock), and
its part of the day. Every field that does not apply is left out.
A leg's flights (`LegList`) hold their day with its weekday in the reply's language, how many
they are, the first and last departure times, the cheapest that seats everyone (`cheapest_id`,
the first listed of two as cheap), each airline's count and cheapest when several fly the day,
and how many more were not listed. The route, the trip's kind and the prices' basis
(`fares_are`) are said in the reply's register, each with its MSA form beside a Saudi reply's.
A result may carry one short `note` only where the data alone would mislead: a full flight, a
route not served, a date outside the window.

A source that could not answer is a `ToolError`: `SEARCH_FAILED`, or `SEARCH_DOWN` when it will
not answer again soon (a rejected key, a rate limit), so no retry is offered; never "no flights".
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, JsonValue
from t2_agentic_voice import Card, ToolResult

from flight_voice.airline.airports import Register
from flight_voice.flight_data.model import Offer, Place, has_seats
from flight_voice.said import Tag, register, words
from flight_voice.said.words import PartOfDay
from flight_voice.tools.results import Duration, said

Network = Literal["mock", "real"]
# The prices' basis in English (`fares_are`), with no digit word: a price said right before
# "one" ("910, one way") reads as one number to the output guard's ID rule, which blocks it.
EACH_WAY: Final = "per person, each way"
PER_PERSON: Final = "per person"
ALL_EACH_WAY: Final = "for all of you, each way"
ALL_OF_YOU: Final = "for all of you"
AS_OF_NOW: Final = ", as of now"
# The Arabic for a party's price, and the real network's "as of now", by register.
_ALL: Final[dict[Register, str]] = {
    "saudi": "لكل المسافرين، رايح بس",
    "msa": "لجميع المسافرين، ذهاب فقط",
}
_ALL_REAL: Final[dict[Register, str]] = {
    "saudi": "للكل، رايح بس",
    "msa": "لجميع المسافرين، ذهاب فقط",
}
_NOW: Final[dict[Register, str]] = {"saudi": "، بسعر الحين", "msa": "، بسعر الآن"}
SEARCH_DOWN: Final = (
    "Flight search is not available on this line right now. Tell the caller so in a few words "
    "and do not offer to try again. Do not say there are no flights."
)


def fares_are(
    tag: Tag, *, round_trip: bool, travelers: int = 1, network: Network = "mock"
) -> tuple[str, str | None]:
    """The prices' basis, said once a call, in the reply's register, and in MSA beside a Saudi
    reply's: per person for one traveler, for all of them for more (a price is the party's, never
    divided here), each way on a round trip, and on the real network as of now. «للشخص» never
    stands beside a party's price."""

    def basis(r: Register) -> str:
        if r == "en":
            if travelers == 1:
                english = EACH_WAY if round_trip else PER_PERSON
            else:
                english = ALL_EACH_WAY if round_trip else ALL_OF_YOU
            return english + (AS_OF_NOW if network == "real" else "")
        if travelers == 1:
            arabic = words.FARE_BASIS[r]
        else:
            arabic = (_ALL_REAL if network == "real" else _ALL)[r]
        return arabic + (_NOW[r] if network == "real" else "")

    return said(basis, tag)


class _Data(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Day(_Data):
    """A day: its ISO date and its weekday in the reply's language."""

    date: str
    weekday: str


class Via(_Data):
    """A connection: the city, how long the wait is, and whether it runs overnight."""

    city: str
    wait: Duration
    overnight: Literal[True] | None = None


class LeanOption(_Data):
    """An offer on its day (the module's docstring)."""

    id: str
    airline: str
    flight: str
    aircraft: str | None = None
    departs: str
    arrives: str
    next_day: Literal[True] | None = None
    duration: Duration
    stops: int
    via: tuple[Via, ...] | None = None
    bus: Literal[True] | None = None
    operated_by: str | None = None
    price: int
    seats_ok: bool | None = None
    part_of_day: PartOfDay


class AirlineCount(_Data):
    """An airline that flies the day: its flights and its cheapest price."""

    airline: str
    flights: int
    cheapest: int


class LegList(_Data):
    """A leg's flights on its day (the module's docstring)."""

    day: Day
    count: int
    first_departs: str | None = None
    last_departs: str | None = None
    cheapest_id: str | None = None
    airlines: tuple[AirlineCount, ...] | None = None
    options: tuple[LeanOption, ...]
    more: int | None = None


def day_of(day: date, tag: Tag) -> Day:
    """`day` with its weekday in the reply's language."""
    return Day(date=day.isoformat(), weekday=words.weekday(day, register(tag)))


def duration(minutes: int) -> Duration:
    return Duration(hours=minutes // 60, minutes=minutes % 60)


def city_of(code: str, name: str | None, get: Callable[[str], Place | None], r: Register) -> str:
    """A layover's city: the directory's name for its airport, else the source's name, else
    its code."""
    place = get(code)
    if place is not None and place.known:
        return place.city(r)
    return name or code


def option_of(
    offer: Offer, tag: Tag, travelers: int, get: Callable[[str], Place | None]
) -> LeanOption:
    """`offer` as the model reads it (the module's docstring); `get` names a layover's city."""
    r = register(tag)
    via = tuple(
        Via(
            city=city_of(w.airport, w.name, get, r),
            wait=duration(w.minutes),
            overnight=True if w.overnight else None,
        )
        for w in offer.layovers
    )
    operated = next((s.operated_by for s in offer.segments if s.operated_by is not None), None)
    return LeanOption(
        id=offer.id,
        airline=offer.carrier.name(r),
        flight=", ".join(offer.flights),
        aircraft=offer.segments[0].aircraft,
        departs=offer.departs.strftime("%H:%M"),
        arrives=offer.arrives.strftime("%H:%M"),
        next_day=True if offer.next_day else None,
        duration=duration(offer.minutes),
        stops=offer.stops,
        via=via or None,
        bus=True if offer.bus else None,
        operated_by=None if operated is None else operated.name(r),
        price=offer.price.amount,
        seats_ok=None if offer.seats_left is None else has_seats(offer, travelers),
        part_of_day=words.part_of_day(offer.departs.time()),
    )


def cheapest_id(options: Sequence[LeanOption]) -> str | None:
    """The cheapest option that seats everyone (`seats_ok` not false), the first listed of two
    as cheap; None when none does."""
    seated = [(o.price, n, o.id) for n, o in enumerate(options) if o.seats_ok is not False]
    return min(seated)[2] if seated else None


def leg_list(
    day: date,
    options: tuple[LeanOption, ...],
    tag: Tag,
    *,
    count: int | None = None,
    airlines: tuple[AirlineCount, ...] | None = None,
) -> LegList:
    """A leg's flights on `day`: their count (`count` over the pool they were listed from, when
    given), first and last times, the cheapest, the airlines, and how many more."""
    times = sorted(o.departs for o in options)
    counted = len(options) if count is None else count
    return LegList(
        day=day_of(day, tag),
        count=counted,
        first_departs=times[0] if times else None,
        last_departs=times[-1] if times else None,
        cheapest_id=cheapest_id(options),
        airlines=airlines,
        options=options,
        more=counted - len(options) if counted > len(options) else None,
    )


def place_route(start: Place, end: Place, r: Register) -> str:
    """A route: "Riyadh to London", «من الرياض للندن» in Saudi, «من الرياض إلى لندن» in MSA."""
    if r == "en":
        return f"{start.city_en} {end.to_city('en')}"
    return f"{start.from_city(r)} {end.to_city(r)}"


def route_said(route: tuple[Place, Place], tag: Tag) -> tuple[str, str | None]:
    """The route in the reply's register, and its MSA form beside a Saudi reply's."""
    return said(lambda r: place_route(*route, r), tag)


def trip_said(one_way: bool, tag: Tag) -> tuple[str, str | None]:
    """The trip's kind in the reply's register, and its MSA form beside a Saudi reply's."""
    return said(lambda r: words.trip_kind(one_way, r), tag)


def full_note(listed: Iterable[LegList], travelers: int, cabin: str) -> str | None:
    """The note on a full flight among the legs `listed`, whichever tool lists them: only when
    one is known to lack seats (`seats_ok` false; a source that counts none never has one)."""
    if not any(o.seats_ok is False for leg in listed for o in leg.options):
        return None
    return f"A flight with seats_ok false has no seats for {travelers} in {cabin}."


def lean_result(
    answer: BaseModel | dict[str, JsonValue], card: Card | None = None, *, done: bool = False
) -> ToolResult:
    """`answer` as the model reads it, its `None` fields left out and its fields by their alias
    ("return"), with its card, whose texts are the result's evidence; `done` for a booking made
    (book.py), which backs the booking's claims."""
    data: dict[str, JsonValue] = (
        answer.model_dump(mode="json", exclude_none=True, by_alias=True)
        if isinstance(answer, BaseModel)
        else {k: v for k, v in answer.items() if v is not None}
    )
    return ToolResult(data=data, card=card, evidence=card.texts() if card else (), done=done)
