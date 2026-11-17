"""What the lean tools give the model: plain data, never a script of what to say (D-113).

A flight option (`LeanOption`) is a flight on its day by a stable id ("T2-401-2026-11-19"), its
name and aircraft (said only when asked, as the cards show them, so every number a card shows is
in the data), its local times at each end, its length, its fare per person in the cabin, whether
it has a seat for every traveler, that it flies nonstop (every flight of the airline does) and its
part of the day.
A leg's flights (`LegList`) hold their day with its weekday in the reply's language, how many
they are, the first and last departure times and the cheapest with seats. The route, the trip's
kind and the fares' basis (`fares_are`) are said in the reply's register, each with its MSA form
beside a Saudi reply's (`route_msa`, `trip_msa`, `fares_are_msa`), as the scripted tools give
them. A result may carry one short `note` only where the data alone would mislead: a
full flight, a route not served, a date outside the window.

`leg_options` builds a leg's options three ways from the airline's flights of a day: the model's
(`LeanOption`), the card's (the scripted tools' `Option`, so round 3's card builders draw them,
the cheapest with seats marked) and the trip draft's (`Shown`), all in departure order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, JsonValue
from t2_agentic_voice import Card, ToolResult

from flight_voice.airline.airports import Code
from flight_voice.airline.schedule import Cabin, Departure
from flight_voice.said import Tag, register, words
from flight_voice.said.words import PartOfDay
from flight_voice.tools.listing import MAX_OPTIONS, marked, options
from flight_voice.tools.results import Duration, Option, said
from flight_voice.trip import Shown

# The fares' basis in English (`fares_are`), with no digit word: a fare said right before "one"
# ("910, one way") reads as one number to the output guard's ID rule, which blocks it.
EACH_WAY: Final = "per person, each way"
PER_PERSON: Final = "per person"


def fares_are(tag: Tag, *, round_trip: bool) -> tuple[str, str | None]:
    """The fares' basis, said once a call, in the reply's register, and in MSA beside a Saudi
    reply's: per person, and on a round trip each way; in Arabic as the scripted tools say it
    («للشخص، رايح بس», «للشخص، ذهاب فقط»)."""
    english = EACH_WAY if round_trip else PER_PERSON
    return said(lambda r: english if r == "en" else words.FARE_BASIS[r], tag)


class _Data(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Day(_Data):
    """A day: its ISO date and its weekday in the reply's language."""

    date: str
    weekday: str


class LeanOption(_Data):
    """A flight on its day (the module's docstring)."""

    id: str
    flight: str
    aircraft: str
    departs: str
    arrives: str
    next_day: Literal[True] | None = None
    duration: Duration
    fare: int
    seats_ok: bool
    nonstop: bool = True
    part_of_day: PartOfDay


class LegList(_Data):
    """A leg's flights on its day (the module's docstring)."""

    day: Day
    count: int
    first_departs: str | None = None
    last_departs: str | None = None
    cheapest_id: str | None = None
    options: tuple[LeanOption, ...]


class Built:
    """One leg's options as the model, the card and the draft hold them, in departure order."""

    def __init__(
        self, data: tuple[LeanOption, ...], card: tuple[Option, ...], shown: tuple[Shown, ...]
    ) -> None:
        self.data, self.card, self.shown = data, card, shown


def day_of(day: date, tag: Tag) -> Day:
    """`day` with its weekday in the reply's language."""
    return Day(date=day.isoformat(), weekday=words.weekday(day, register(tag)))


def option_id(code: str, flight: int, day: date) -> str:
    """A flight's id on its day: "T2-401-2026-11-19"."""
    return f"{code}-{flight}-{day.isoformat()}"


def route_said(route: tuple[Code, Code], tag: Tag) -> tuple[str, str | None]:
    """The route in the reply's register, and its MSA form beside a Saudi reply's."""
    return said(lambda r: words.route(*route, r), tag)


def trip_said(one_way: bool, tag: Tag) -> tuple[str, str | None]:
    """The trip's kind in the reply's register, and its MSA form beside a Saudi reply's."""
    return said(lambda r: words.trip_kind(one_way, r), tag)


def leg_options(
    found: Sequence[Departure],
    *,
    cabin: Cabin,
    travelers: int,
    tag: Tag,
    code: str,
    name: Callable[[int], str],
) -> Built:
    """The flights of `found` that sell `cabin`, at most `MAX_OPTIONS`, in departure order, as
    the model, the card and the draft hold them (the module's docstring)."""
    kept = [d for d in found if cabin in d.flight.cabins][:MAX_OPTIONS]
    each = [options([d], cabin=cabin, travelers=travelers, tag=tag, name=name)[0] for d in kept]
    card = marked([o.model_copy(update={"n": n}) for n, o in enumerate(each, start=1)])
    data = tuple(
        LeanOption(
            id=option_id(code, d.flight.number, d.day),
            flight=o.flight,
            aircraft=o.aircraft,
            departs=o.departs,
            arrives=o.arrives,
            next_day=o.next_day,
            duration=o.duration,
            fare=o.fare_sar,
            seats_ok=o.seats_ok,
            part_of_day=words.part_of_day(d.flight.departs),
        )
        for d, o in zip(kept, card, strict=True)
    )
    shown = tuple(
        Shown(n=o.n, flight=d.flight.number, day=d.day) for d, o in zip(kept, card, strict=True)
    )
    return Built(data, card, shown)


def leg_list(day: date, built: Built, tag: Tag) -> LegList:
    """A leg's flights on `day`, with their count, first and last times and the cheapest."""
    times = sorted(o.departs for o in built.data)
    cheapest = next((d.id for d, o in zip(built.data, built.card, strict=True) if o.mark), None)
    return LegList(
        day=day_of(day, tag),
        count=len(built.data),
        first_departs=times[0] if times else None,
        last_departs=times[-1] if times else None,
        cheapest_id=cheapest,
        options=built.data,
    )


def lean_result(answer: BaseModel | dict[str, JsonValue], card: Card | None = None) -> ToolResult:
    """`answer` as the model reads it, its `None` fields left out and its fields by their alias
    ("return"), with its card, whose texts are the result's evidence."""
    data: dict[str, JsonValue] = (
        answer.model_dump(mode="json", exclude_none=True, by_alias=True)
        if isinstance(answer, BaseModel)
        else {k: v for k, v in answer.items() if v is not None}
    )
    return ToolResult(data=data, card=card, evidence=card.texts() if card else ())
