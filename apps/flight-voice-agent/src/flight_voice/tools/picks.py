"""A caller's pick of a listed flight, as the talker passes it (`Choice`), and the code that
reads it against the options last listed for that leg, in the order said (`pick`).

The talker passes the pick in the kind the caller said it, never a flight it worked out: by its
number in the list ("option three", «رقم ثلاثة»), the cheapest, the dearest, the earliest, the
latest, its part of the day ("the afternoon one", «اللي الظهر»), a departure time the caller
said or a fare the caller said. Each kind's class docstring is its description in the tools'
schema. A pick names one option, or it is unclear and the options it could mean are said back;
"the cheapest" is the one the listing marked, the cheapest with a seat for every traveler, and
"the dearest" the dearest with one, each the first listed of two at one fare; a fare said names
every option at that fare in the trip's cabin.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import Cabin, Departure, departure, find_flight
from flight_voice.said.words import PartOfDay, part_of_day
from flight_voice.trip import Shown

# The pick's description in choose_flight's and compare_cabins' schemas alike.
CHOICE: Final = (
    "The caller's pick, as they said it; never a flight you worked out, nor the time or number "
    "of the flight it means, even one a tool already named: a part of the day goes as "
    "part_of_day, a comparison of when it leaves as earliest or latest, a comparison of fares "
    "as cheapest or dearest, a fare they said as fare, the only flight listed as its number."
)


class _Pick(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ByNumber(_Pick):
    """The option by its place in the list, only when the caller said a number or an order word
    ("option three", «رقم ثلاثة») or picked the only flight listed. A comparison of when it
    leaves is earliest or latest; one by a part of the day is part_of_day."""

    pick: Literal["number"] = "number"
    n: int = Field(ge=1, le=4)


class Cheapest(_Pick):
    """The cheapest option with seats: "the lowest fare", «أرخص وحدة»."""

    pick: Literal["cheapest"] = "cheapest"


class Dearest(_Pick):
    """The dearest option with seats, whenever the caller picks by the highest fare, a
    comparison too: "the priciest one", «اللي سعرها أعلى»; never its number."""

    pick: Literal["dearest"] = "dearest"


class Earliest(_Pick):
    """The option that leaves first, whenever the caller picks by how early it leaves,
    a comparison too: "whichever leaves soonest", «اللي تطلع بدري»; never its number."""

    pick: Literal["earliest"] = "earliest"


class Latest(_Pick):
    """The option that leaves last, whenever the caller picks by how late it leaves,
    a comparison too: "the last flight out", «آخر وحدة تطلع»; never its number."""

    pick: Literal["latest"] = "latest"


class ByPart(_Pick):
    """The option that leaves in a part of the day the caller named, even when you know its time
    or its number: "the afternoon one", «اللي الظهر», «الرحلة الليلية».
    Morning is 05:00 to 11:59, afternoon 12:00 to 17:59, evening 18:00 to 21:59,
    night 22:00 to 04:59."""

    pick: Literal["part_of_day"] = "part_of_day"
    part: PartOfDay


class ByTime(_Pick):
    """The option that leaves at a time the caller said themselves, as "HH:MM": "the 7:45".
    Never for a flight they named another way, even one a tool gave with its time."""

    pick: Literal["time"] = "time"
    departs: str = Field(pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")


class ByFare(_Pick):
    """The option at a fare the caller said themselves, in riyals, as a whole number: "the one
    for 1250", «اللي بـ 980». Never for a flight they named another way, nor its number."""

    pick: Literal["fare"] = "fare"
    fare_sar: int = Field(ge=1)


Choice = Annotated[
    ByNumber | Cheapest | Dearest | Earliest | Latest | ByPart | ByTime | ByFare,
    Field(discriminator="pick"),
]


def departure_of(shown: Shown) -> Departure:
    """The listed option's flight on its day."""
    flight = find_flight(shown.flight)
    if flight is None:  # the draft holds only flights the timetable listed
        raise LookupError("a listed flight is not in the timetable")
    return departure(flight, shown.day)


def pick(choice: Choice, shown: tuple[Shown, ...], cabin: Cabin, travelers: int) -> list[Shown]:
    """The options of `shown` that `choice` names: one when it is clear, none or several when it
    is not, in the order listed."""
    if isinstance(choice, ByNumber):
        return [s for s in shown if s.n == choice.n]
    if isinstance(choice, Earliest | Latest):
        ordered = sorted(shown, key=lambda s: departure_of(s).departs_at)
        return ordered[:1] if isinstance(choice, Earliest) else ordered[-1:]
    if isinstance(choice, ByPart):
        return [s for s in shown if part_of_day(departure_of(s).flight.departs) == choice.part]
    if isinstance(choice, ByTime):
        hours, minutes = choice.departs.split(":")
        at = f"{int(hours):02d}:{minutes}"
        return [s for s in shown if departure_of(s).departs_at.strftime("%H:%M") == at]
    if isinstance(choice, ByFare):
        return [s for s in shown if fare(departure_of(s), cabin) == choice.fare_sar]
    selling = [s for s in shown if _seats(s, cabin) >= travelers] or list(shown)
    priced = [(f, s.n, s) for s in selling if (f := fare(departure_of(s), cabin)) is not None]
    if not priced:
        return []
    if isinstance(choice, Dearest):  # the dearest, the first listed of two as dear
        return [max(priced, key=lambda item: (item[0], -item[1]))[2]]
    return [min(priced, key=lambda item: (item[0], item[1]))[2]]


def _seats(shown: Shown, cabin: Cabin) -> int:
    flight = find_flight(shown.flight)
    return 0 if flight is None else seats_left(flight, shown.day, cabin)
