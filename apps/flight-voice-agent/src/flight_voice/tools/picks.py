"""A caller's pick of a listed flight, as the talker passes it (`Choice`), and the code that
reads it against the options last listed for that leg, in the order said (`pick`).

The talker passes the pick as the caller made it, never a flight it worked out: by its number in
the list ("the second one", «الثانية»), the cheapest, the earliest, the latest, its part of the
day ("the morning one", «حقت الصبح») or its departure time. A pick names one option, or it is
unclear and the options it could mean are said back; "the cheapest" is the one the listing
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
    """The option by its number in the list, as said: «الثانية», "the second one"."""

    pick: Literal["number"] = "number"
    n: int = Field(ge=1, le=4)


class Cheapest(_Pick):
    """The cheapest option with seats: «الأرخص», "the cheaper one"."""

    pick: Literal["cheapest"] = "cheapest"


class Earliest(_Pick):
    """The option that leaves first."""

    pick: Literal["earliest"] = "earliest"


class Latest(_Pick):
    """The option that leaves last."""

    pick: Literal["latest"] = "latest"


class ByPart(_Pick):
    """The option that leaves in a part of the day: "the morning one", «حقت الصبح»."""

    pick: Literal["part_of_day"] = "part_of_day"
    part: PartOfDay


class ByTime(_Pick):
    """The option that leaves at a time, as "HH:MM": "the 9:10"."""

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
