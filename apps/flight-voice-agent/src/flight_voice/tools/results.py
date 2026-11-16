"""What the flight tools give the talker: a pydantic model per result, each holding its `status`
(a word from a closed set), its facts as machine values (times "09:10", fares 2450, durations
{"hours": 7, "minutes": 5}, dates by their ISO form, day, month and weekday), the words with no
number in them in the reply's language (`*_said`, and `*_said_msa` beside a Saudi reply's), and
`say`, one of the app's fixed strings (`SAY`) telling the talker what to say next, never built
from the caller's words or any free text.

A listing holds at most four options, in departure order, the cheapest with seats marked, and
the fare's basis ("per person, one way") said once. A read of the airline that fails is never a
result: it is a `ToolError` whose message names the failure and forbids reading it as nothing
found (`SEARCH_FAILED`, `PROFILE_FAILED`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from t2_agentic_voice import Card, ToolResult

from flight_voice.airline.airports import Code, Register
from flight_voice.airline.dates import Problem
from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import Cabin, Departure
from flight_voice.said import Tag, msa_too, register, words
from flight_voice.trip import LegKind

# The most options a listing holds, and the most the talker says aloud in a turn.
MAX_OPTIONS: Final = 4
SAID_ALOUD: Final = 3

SEARCH_FAILED: Final = (
    "The flight search did not answer. Tell the caller you could not check flights just now and "
    "offer to try again in a moment. Do not say there are no flights or no seats."
)
PROFILE_FAILED: Final = (
    "The travel profile did not load. Tell the caller you could not open their travel history "
    "just now. Do not say they have no trips or no bookings."
)
_LISTED: Final = (
    "Say these flights, at most three, each by its departure time and fare, the cheapest "
    "marked. Say once that fares are one way, per person. Then ask which one they want. Do not "
    "say flight numbers."
)
_MORE: Final = (
    "Say three of these flights, the cheapest among them, each by its departure time and fare, "
    "then how many more there are and when they leave. Say once that fares are one way, per "
    "person. Then ask which one they want. Do not say flight numbers."
)
_FULL: Final = " A flight with seats_ok false is full in this cabin: if you name it, say so."
SAY: Final[dict[str, str]] = {
    "listed": _LISTED,
    "listed_more": _MORE,
    "listed_full": _LISTED + _FULL,
    "listed_more_full": _MORE + _FULL,
    "not_served_city": "Say we do not fly there, name the cities we fly to, and ask where they "
    "would like to go.",
    "not_served_route": "Say we fly only to and from Riyadh, with no connections, so each part "
    "would be its own trip through Riyadh. Ask how they would like to go on.",
    "past": "Say that day has passed and ask for another day.",
    "beyond_window": "Say bookings open only up to last_day, with its weekday, and ask for a "
    "day on or before it.",
    "no_such_day": "Say that day does not exist in that month and ask for the day again.",
    "return_before_departure": "Say that return is before the departure and ask when they "
    "would like to come back.",
    "return_only": "Ask which day they would like to leave.",
    "needs_return_date": "Ask when they would like to come back. Do not list flights yet.",
    "cabin_not_offered": "Say that cabin is not offered on this route, offer the cabins in "
    "offered, and ask which they would like. Do not list flights yet.",
    "no_flights_that_day": "Say there is no flight that day and offer these days.",
    "no_seats": "Say the flights that day are full in this cabin for this many travelers, and "
    "offer the cabins in cabins_with_seats or another day.",
}


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
    times at each end, its length, its part of the day said, its fare per person in the cabin,
    whether it has a seat for every traveler, and the mark on the cheapest."""

    n: int
    flight: str
    aircraft: str
    departs: str
    arrives: str
    next_day: Literal[True] | None = None
    duration: Duration
    part_of_day_said: str
    part_of_day_said_msa: str | None = None
    fare_sar: int
    seats_ok: bool
    mark: Literal["cheapest"] | None = None


class Listing(_Result):
    """A leg's flights on its day (status `ok`), and the trip's return date on an outbound one."""

    status: Literal["ok"] = "ok"
    leg: LegKind
    route_said: str
    route_said_msa: str | None = None
    date: DateSaid
    return_date: DateSaid | None = None
    options: tuple[Option, ...]
    more: int | None = None
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
    """A day whose flights are all short of seats in the cabin, and the cabins that have them."""

    status: Literal["no_seats"] = "no_seats"
    leg: LegKind
    date: DateSaid
    cabin: Cabin
    travelers: int
    cabins_with_seats: tuple[Cabin, ...]
    say: str = SAY["no_seats"]


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


def result(answer: BaseModel, card: Card | None = None) -> ToolResult:
    """`answer` as the talker reads it, its `None` fields left out, with its card, whose texts
    are the result's evidence."""
    data = answer.model_dump(mode="json", exclude_none=True)
    return ToolResult(data=data, card=card, evidence=card.texts() if card else ())
