"""What the flight tools give the talker: a pydantic model per result, each holding its `status`
(a word from a closed set), its facts as machine values (times "09:10", fares 2450, durations
{"hours": 7, "minutes": 5}, dates by their ISO form, day, month and weekday), the words with no
number in them in the reply's language (`*_said`, and `*_said_msa` beside a Saudi reply's), and
`say`, one of the app's fixed strings (`SAY`) telling the talker what to say next, never built
from the caller's words or any free text.

A listing (`listing.py`) holds at most four options, numbered in the order said, the cheapest
with seats marked, and the fare's basis ("per person, one way") said once; a fourth is said by
its part of the day. A first outbound listing is said from its day and its weekday, in place of
the caller's request said back (`listed`); a return listing, after the choice said back, is not
(`return_listed`). A listing after one of another day in the call is said from its day, without
the basis again (`relisted`). A read of the airline that fails is never a result: it is
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
from flight_voice.trip import LegKind

SEARCH_FAILED: Final = (
    "The flight search did not answer. Tell the caller you could not check flights just now and "
    "offer to try again in a moment. Do not say there are no flights or no seats."
)
PROFILE_FAILED: Final = (
    "The travel profile did not load. Tell the caller you could not open their travel history "
    "just now. Do not say they have no trips or no bookings."
)
_THREE: Final = (
    "these flights, at most three, each by its departure time and fare, the cheapest marked."
)
_FOUR: Final = (
    "options 1 to 3 in order, each by its departure time and fare, the cheapest marked, then that "
    "there is one more and its part of the day (part_of_day_said), never its time or its fare."
)
_ONCE: Final = " Say once that fares are one way, per person."
_NOT_AGAIN: Final = " Do not say again that fares are one way, per person."
_ASK: Final = " Then ask which one they want. Do not say flight numbers."
_DAY: Final = "Say the day with its weekday first, in place of saying their request back, then "
_NEW_DAY: Final = "Say the new day with its weekday first, then "
_FULL: Final = " A flight with seats_ok false is full in this cabin: if you name it, say so."
SAY: Final[dict[str, str]] = {
    "listed": _DAY + _THREE + _ONCE + _ASK,
    "listed_more": _DAY + _FOUR + _ONCE + _ASK,
    "listed_full": _DAY + _THREE + _ONCE + _ASK + _FULL,
    "listed_more_full": _DAY + _FOUR + _ONCE + _ASK + _FULL,
    "return_listed": "Say " + _THREE + _ONCE + _ASK,
    "return_listed_more": "Say " + _FOUR + _ONCE + _ASK,
    "return_listed_full": "Say " + _THREE + _ONCE + _ASK + _FULL,
    "return_listed_more_full": "Say " + _FOUR + _ONCE + _ASK + _FULL,
    "relisted": _NEW_DAY + _THREE + _NOT_AGAIN + _ASK,
    "relisted_more": _NEW_DAY + _FOUR + _NOT_AGAIN + _ASK,
    "relisted_full": _NEW_DAY + _THREE + _NOT_AGAIN + _ASK + _FULL,
    "relisted_more_full": _NEW_DAY + _FOUR + _NOT_AGAIN + _ASK + _FULL,
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
    "no_seats_flight": "Say that flight is full in this cabin for this many travelers, and "
    "offer the cabins in cabins_with_seats or the other flights in other_flights.",
    "nothing_listed": "Search first.",
    "unclear_choice": "Say the flights the caller could mean, each by its departure time and "
    "fare, and ask which one they want.",
    "chosen_then_return": "Say the choice back in a few words, then the return flights, at most "
    "three, and how many more if there are more, and ask which one. Say once that fares are one "
    "way, per person.",
    "chosen_then_outbound": "Say the choice back in a few words, then ask which outbound flight "
    "they want.",
    "chosen_needs_return": "Say the choice back in a few words, then ask when they would like to "
    "come back.",
    "chosen_return_full": "Say the choice back in a few words, then that no return flight that "
    "day has a seat in this cabin for this many travelers, and offer another return day or cabin.",
    "complete": "Call book_trip now and say nothing yourself; the caller hears the trip read back "
    "and is asked to confirm it.",
    "changed": "Say what changed in a few words, then ask for what is still missing.",
    "changed_relist": "Say what changed in a few words, then these flights again with their "
    "new fares, at most three, and ask which one they want.",
    "changed_lost": "Say what changed, then that the flight chosen for that leg has no seats "
    "for it now, then that leg's flights, at most three, and ask which one they want.",
    "changed_needs_return": "Say what changed, then ask when they would like to come back.",
    "trip": "Answer from this trip. If something is missing, ask for the first thing missing.",
    "trip_empty": "Nothing is planned yet. Ask where they would like to go.",
    "calendar": "Say the three cheapest days with their fares, then ask which day suits them.",
    "cabins": "Say each cabin's fare on this flight, one way, per person, and ask which cabin "
    "they want. Then wait for their answer; call change_trip only for a cabin the caller asked "
    "for.",
    "profile": "Answer from these counts. Say a past trip as one they flew, never as one you "
    "booked. Never read a booking reference unless the caller asks for it.",
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
    those listed when it names none)."""

    status: Literal["unclear_choice"] = "unclear_choice"
    leg: LegKind
    options: tuple[Option, ...]
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
