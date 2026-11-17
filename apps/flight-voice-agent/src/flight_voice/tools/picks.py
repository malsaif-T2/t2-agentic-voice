"""A caller's pick of a listed flight, as the talker passes it (`Choice`), and the code that
reads it against the options last listed for that leg, in the order said (`pick`).

The talker passes the pick in the kind the caller said it, never a flight it worked out: by its
number in the list ("option three", «رقم ثلاثة»), the cheapest, the earliest, the latest, its
part of the day ("the afternoon one", «اللي الظهر») or a departure time the caller said. Each
kind's class docstring is its description in the tools' schema. A pick names one option, or it
is unclear and the options it could mean are said back; "the cheapest" is the one the listing
marked, the cheapest with a seat for every traveler.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import Cabin, Departure, departure, find_flight
from flight_voice.said.words import PartOfDay, part_of_day
from flight_voice.trip import Shown


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


Choice = Annotated[
    ByNumber | Cheapest | Earliest | Latest | ByPart | ByTime, Field(discriminator="pick")
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
    selling = [s for s in shown if _seats(s, cabin) >= travelers] or list(shown)
    priced = [(fare(departure_of(s), cabin), s.n, s) for s in selling]
    kept = [(f, n, s) for f, n, s in priced if f is not None]
    return [min(kept, key=lambda item: (item[0] or 0, item[1]))[2]] if kept else []


def _seats(shown: Shown, cabin: Cabin) -> int:
    flight = find_flight(shown.flight)
    return 0 if flight is None else seats_left(flight, shown.day, cabin)
