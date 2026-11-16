"""The mock airline's timetable: its nine routes out of Riyadh and back, the flights each flies a
day, their numbers, aircraft and durations, and each flight on a date with its departure and
arrival in local time at each end.

Every route starts or ends in Riyadh; a trip between two other cities is not sold (no
connections). Times are local at each airport; arrival is departure plus the duration, said in
the arrival airport's offset, with `next_day` when the local date changes. Outbound flight numbers
are odd, return ones even. Every route flies every day but Singapore's, which has no flight
either way on Tuesdays. First class is sold only on the 787-9.

Each airport keeps one offset all year (airports.py), which holds only until Europe's summer
time begins on 2027-03-28; so no day after `LAST_DAY` is ever sold (`OutsideTimetableError`),
and the booking window, today to 120 days on, ends there at the latest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Final, Literal, get_args

from flight_voice.airline.airports import AIRPORTS, HOME, Airport, Code

Aircraft = Literal["A320neo", "A321neo", "A330-300", "787-9"]
Cabin = Literal["economy", "business", "first"]
CABINS: Final[tuple[Cabin, ...]] = get_args(Cabin)
# The aircraft that carry a first-class cabin.
FIRST_CLASS: Final[frozenset[Aircraft]] = frozenset({"787-9"})
# The days a booking may be made for: from today to today plus this many days.
WINDOW_DAYS: Final = 120
# The last day the fixed offsets hold: Europe's summer time begins the day after.
LAST_DAY: Final = date(2027, 3, 27)
# Python's weekday of a Tuesday, Singapore's day with no flight.
_TUESDAY: Final = 1


class OutsideTimetableError(ValueError):
    """A day past `LAST_DAY`, where the fixed offsets would put a wrong local time."""


@dataclass(frozen=True)
class _Route:
    """One route's flights, out of Riyadh and back: the local departure times at each end, the
    durations, the aircraft and the numbers, in the same order as the times."""

    out: tuple[str, ...]
    back: tuple[str, ...]
    out_minutes: int
    back_minutes: int
    aircraft: Aircraft
    out_numbers: tuple[int, ...]
    back_numbers: tuple[int, ...]


def _hm(hours: int, minutes: int) -> int:
    return hours * 60 + minutes


_ROUTES: Final[dict[Code, _Route]] = {
    "JED": _Route(
        ("06:00", "10:30", "15:00", "21:00"),
        ("07:45", "12:30", "17:15", "23:00"),
        _hm(1, 50),
        _hm(1, 45),
        "A320neo",
        (101, 103, 105, 107),
        (102, 104, 106, 108),
    ),
    "DXB": _Route(
        ("07:15", "13:40", "20:30"),
        ("10:20", "17:05", "23:55"),
        _hm(1, 55),
        _hm(2, 0),
        "A321neo",
        (201, 203, 205),
        (202, 204, 206),
    ),
    "DOH": _Route(
        ("08:00", "14:20", "19:45"),
        ("10:40", "17:00", "22:30"),
        _hm(1, 25),
        _hm(1, 30),
        "A320neo",
        (251, 253, 255),
        (252, 254, 256),
    ),
    "CAI": _Route(
        ("09:30", "18:15"),
        ("13:20", "22:40"),
        _hm(2, 45),
        _hm(2, 35),
        "A321neo",
        (301, 303),
        (302, 304),
    ),
    "IST": _Route(
        ("02:10", "11:50"),
        ("09:05", "18:30"),
        _hm(4, 30),
        _hm(4, 15),
        "A321neo",
        (351, 353),
        (352, 354),
    ),
    "LHR": _Route(
        ("09:10", "14:40"),
        ("16:00", "21:45"),
        _hm(7, 5),
        _hm(6, 20),
        "787-9",
        (401, 403),
        (402, 404),
    ),
    "CDG": _Route(
        ("01:55", "08:35"),
        ("11:30", "15:10"),
        _hm(6, 35),
        _hm(6, 5),
        "787-9",
        (451, 453),
        (452, 454),
    ),
    "BOM": _Route(
        ("03:20", "16:45"),
        ("09:30", "21:15"),
        _hm(4, 0),
        _hm(4, 30),
        "A330-300",
        (501, 503),
        (502, 504),
    ),
    "SIN": _Route(("22:05",), ("08:40",), _hm(8, 20), _hm(9, 10), "787-9", (601,), (602,)),
}


@dataclass(frozen=True)
class Flight:
    """One flight of the timetable, flown every day it flies: its number, its two airports,
    its local departure time, its duration and its aircraft."""

    number: int
    origin: Code
    destination: Code
    departs: time
    duration: timedelta
    aircraft: Aircraft

    @property
    def cabins(self) -> tuple[Cabin, ...]:
        """The cabins sold on it: first class only on the aircraft that carry one."""
        return CABINS if self.aircraft in FIRST_CLASS else ("economy", "business")


@dataclass(frozen=True)
class Departure:
    """A flight on a date: when it leaves, in the origin's local time, and when it lands, in
    the destination's; `next_day` when it lands on a later local date than it left."""

    flight: Flight
    day: date
    departs_at: datetime
    arrives_at: datetime

    @property
    def next_day(self) -> bool:
        """Whether it lands on a later local date than the one it left on."""
        return self.arrives_at.date() > self.day


def route_served(origin: Code, destination: Code) -> bool:
    """Whether the airline flies `origin` to `destination`: one of them Riyadh, not both."""
    return origin != destination and HOME in (origin, destination)


def flights(origin: Code, destination: Code) -> tuple[Flight, ...]:
    """The route's flights in departure order, or none when the route is not served."""
    if not route_served(origin, destination):
        return ()
    outbound = origin == HOME
    other = destination if outbound else origin
    route = _ROUTES[other]
    times = route.out if outbound else route.back
    numbers = route.out_numbers if outbound else route.back_numbers
    minutes = route.out_minutes if outbound else route.back_minutes
    return tuple(
        Flight(
            n,
            origin,
            destination,
            time.fromisoformat(t),
            timedelta(minutes=minutes),
            route.aircraft,
        )
        for t, n in zip(times, numbers, strict=True)
    )


def flies_on(origin: Code, destination: Code, day: date) -> bool:
    """Whether the route has a flight on `day`: every day, but none to or from Singapore on a
    Tuesday."""
    if not route_served(origin, destination):
        return False
    return not ("SIN" in (origin, destination) and day.weekday() == _TUESDAY)


def departures(origin: Code, destination: Code, day: date) -> tuple[Departure, ...]:
    """Each flight of the route on `day`, in departure order; none on a day it does not fly.
    A day past `LAST_DAY` raises `OutsideTimetableError`."""
    if day > LAST_DAY:
        raise OutsideTimetableError(f"the timetable ends on {LAST_DAY.isoformat()}")
    if not flies_on(origin, destination, day):
        return ()
    return tuple(departure(f, day) for f in flights(origin, destination))


def departure(flight: Flight, day: date) -> Departure:
    """`flight` on `day`, its arrival in the destination's local time."""
    start: Airport = AIRPORTS[flight.origin]
    end: Airport = AIRPORTS[flight.destination]
    leaves = datetime.combine(day, flight.departs, tzinfo=_zone(start))
    lands = (leaves + flight.duration).astimezone(UTC).astimezone(_zone(end))
    return Departure(flight, day, leaves, lands)


def find_flight(number: int) -> Flight | None:
    """The flight with `number`, on any route, or `None`."""
    for other in _ROUTES:
        for flight in (*flights(HOME, other), *flights(other, HOME)):
            if flight.number == number:
                return flight
    return None


def window(today: date) -> tuple[date, date]:
    """The first and last day a booking may be made for: today, and 120 days on or `LAST_DAY`,
    whichever comes first."""
    return today, min(today + timedelta(days=WINDOW_DAYS), LAST_DAY)


def _zone(airport: Airport) -> timezone:
    return timezone(airport.utc_offset)
