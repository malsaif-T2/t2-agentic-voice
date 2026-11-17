"""What the flight tools give the talker: a pydantic model per result, each holding its `status`
(a word from a closed set), its facts as machine values (times "09:10", fares 2450, durations
{"hours": 7, "minutes": 5}, dates by their ISO form, day, month and weekday), the words with no
number in them in the reply's language (`*_said`, and `*_said_msa` beside a Saudi reply's), and
`say`, one of the app's fixed strings (`SAY`, says.py) telling the talker what to say next, never
built from the caller's words or any free text.

A listing (`listing.py`) holds at most four options, numbered in the order said, the cheapest
with seats marked, each flying nonstop. A read of the airline that fails is never a result: it is
a `ToolError` whose message names the failure and forbids reading it as nothing found
(`SEARCH_FAILED`, `PROFILE_FAILED`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from t2_agentic_voice import Card, ToolResult

from flight_voice.airline.airports import Register
from flight_voice.airline.dates import Problem
from flight_voice.airline.schedule import Cabin
from flight_voice.said import Tag, msa_too, register, words
from flight_voice.tools.says import SAY as SAY  # the fixed strings, given here with the models
from flight_voice.trip import LegKind

SEARCH_FAILED: Final = (
    "The flight search did not answer. Tell the caller you could not check flights just now and "
    "offer to try again in a moment. Do not say there are no flights or no seats."
)
PROFILE_FAILED: Final = (
    "The travel profile did not load. Tell the caller you could not open their travel history "
    "just now. Do not say they have no trips or no bookings."
)


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Duration(_Result):
    """A flight's length."""

    hours: int
    minutes: int


class DateSaid(_Result):
    """A resolved date: its ISO form, its day, and its month and weekday in the reply's
    language; `assumed` when the code chose its month or year, so the talker says it back."""

    iso: str
    day: int
    month: str
    weekday: str
    assumed: Literal[True] | None = None


class Option(_Result):
    """A flight listed to the caller: its place in the list, its name and aircraft, its local
    times at each end, its length, that it flies nonstop (every flight of the airline does), its
    part of the day said, its fare per person in the cabin, whether it has a seat for every
    traveler, and the mark on the cheapest."""

    n: int
    flight: str
    aircraft: str
    departs: str
    arrives: str
    next_day: Literal[True] | None = None
    duration: Duration
    nonstop: bool = True
    part_of_day_said: str
    part_of_day_said_msa: str | None = None
    fare_sar: int
    seats_ok: bool
    mark: Literal["cheapest"] | None = None


class Listing(_Result):
    """A leg's flights on its day (status `ok`), how many they are and the first and last
    departure times among them, and the trip's return date on an outbound one."""

    status: Literal["ok"] = "ok"
    leg: LegKind
    route_said: str
    route_said_msa: str | None = None
    date: DateSaid
    return_date: DateSaid | None = None
    options: tuple[Option, ...]
    count: int
    first_departs: str
    last_departs: str
    travelers: int
    cabin: Cabin
    cabin_said: str
    cabin_said_msa: str | None = None
    fare_basis_said: str
    fare_basis_said_msa: str | None = None
    say: str


class NotServed(_Result):
    """A city the airline does not serve, or a route it does not fly; the cities it serves."""

    status: Literal["not_served"] = "not_served"
    served_said: str
    served_said_msa: str | None = None
    say: str


class DateIssue(_Result):
    """A date that cannot be used, and the last day a booking may be made for."""

    status: Literal["date_problem"] = "date_problem"
    leg: LegKind
    problem: Problem
    last_day: DateSaid
    say: str


class NeedsReturn(_Result):
    """A round trip asked with no return date: nothing searched."""

    status: Literal["needs_return_date"] = "needs_return_date"
    say: str = SAY["needs_return_date"]


class CabinNotOffered(_Result):
    """A cabin the route's aircraft do not carry, and the cabins they do."""

    status: Literal["cabin_not_offered"] = "cabin_not_offered"
    cabin: Cabin
    offered: tuple[Cabin, ...]
    say: str = SAY["cabin_not_offered"]


class NoFlights(_Result):
    """A day the route has no flight, and the nearest days it has."""

    status: Literal["no_flights_that_day"] = "no_flights_that_day"
    leg: LegKind
    date: DateSaid
    nearest: tuple[DateSaid, ...]
    say: str = SAY["no_flights_that_day"]


class NoSeats(_Result):
    """A day whose flights are all short of seats in the cabin (or a picked flight that is), the
    cabins that have them, and, for a picked flight, the other flights that day with seats."""

    status: Literal["no_seats"] = "no_seats"
    leg: LegKind
    date: DateSaid
    cabin: Cabin
    travelers: int
    cabins_with_seats: tuple[Cabin, ...]
    other_flights: tuple[Option, ...] = ()
    say: str = SAY["no_seats"]


class NothingListed(_Result):
    """A pick for a leg whose flights were not listed yet."""

    status: Literal["nothing_listed"] = "nothing_listed"
    leg: LegKind
    say: str = SAY["nothing_listed"]


class Unclear(_Result):
    """A pick that names no listed option, or more than one: the options it could mean (all
    those listed when it names none), how many they are and the first and last departure times
    among them (listing.py's `unclear`)."""

    status: Literal["unclear_choice"] = "unclear_choice"
    leg: LegKind
    options: tuple[Option, ...]
    count: int = 0
    first_departs: str | None = None
    last_departs: str | None = None
    say: str = SAY["unclear_choice"]


def said(form: Callable[[Register], str], tag: Tag) -> tuple[str, str | None]:
    """`form` in the reply's register, and in MSA beside a Saudi reply's when it differs."""
    first = form(register(tag))
    msa = form("msa") if msa_too(tag) else None
    return first, None if msa == first else msa


def date_said(day: date, tag: Tag, *, assumed: bool = False) -> DateSaid:
    """`day` as a result gives it, in the reply's language."""
    r = register(tag)
    return DateSaid(
        iso=day.isoformat(),
        day=day.day,
        month=words.month(day.month, r),
        weekday=words.weekday(day, r),
        assumed=True if assumed else None,
    )


def result(answer: BaseModel, card: Card | None = None) -> ToolResult:
    """`answer` as the talker reads it, its `None` fields left out, with its card, whose texts
    are the result's evidence."""
    data = answer.model_dump(mode="json", exclude_none=True)
    return ToolResult(data=data, card=card, evidence=card.texts() if card else ())
