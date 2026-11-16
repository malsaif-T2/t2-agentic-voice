"""The mock airline's fares and seats: every fare one way, per person, in Saudi riyals, in whole
tens; the fare calendar, each day's cheapest fare in a cabin; and the seats left in each cabin.

Nothing is random. What varies by flight and date comes from SHA-256 of a fixed seed and the
value's parts (`h`), never Python's `hash()`, which is salted per process, so every process and
every run gives the same fare. Arithmetic is exact (fractions), rounded half up to tens once per
step:

    economy  = round10(base x weekday x season x hour x deal x jitter)
    business = round10(economy x 3.2)
    first    = round10(economy x 5.5)

The weekday is the departure's (the Saudi weekend is Friday and Saturday); the seasons are the
mock's own winter break and Eid days; a departure before 06:00 local is cheaper; a deal day, about
one in thirteen, takes a fifth off every flight of the route that day.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Final

from flight_voice.airline.airports import HOME, Code
from flight_voice.airline.schedule import Cabin, Departure, Flight, departures

SEED: Final = "t2air-2026-11"
# The base economy fare of each route, the same both ways, by the city that is not Riyadh.
BASE: Final[dict[Code, int]] = {
    "JED": 390,
    "DXB": 650,
    "DOH": 520,
    "CAI": 980,
    "IST": 1450,
    "LHR": 2350,
    "CDG": 2250,
    "BOM": 1350,
    "SIN": 2750,
}
# By Python's weekday, Monday first.
WEEKDAY: Final = tuple(
    Fraction(f) for f in ("0.90", "0.85", "0.95", "1.20", "1.10", "1.05", "1.00")
)
# The mock's seasons, first and last day each, and their factor.
SEASONS: Final = (
    (date(2026, 12, 17), date(2027, 1, 3), Fraction("1.30")),
    (date(2027, 3, 5), date(2027, 3, 14), Fraction("1.25")),
)
EARLY: Final = Fraction("0.90")  # a departure from 00:00 to 05:59 local
DEAL: Final = Fraction("0.80")
JITTER: Final = (Fraction("0.97"), Fraction("1.00"), Fraction("1.03"))
CABIN_FACTOR: Final[dict[Cabin, Fraction]] = {
    "economy": Fraction(1),
    "business": Fraction("3.2"),
    "first": Fraction("5.5"),
}


def h(*parts: str) -> int:
    """The seeded number of `parts`: SHA-256 of the seed and the parts joined by "|", its first
    twelve hex digits read as a number."""
    digest = hashlib.sha256("|".join([SEED, *parts]).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def round10(value: Fraction) -> int:
    """`value` rounded to the nearest ten riyals, a half rounded up."""
    return int((value / 10 + Fraction(1, 2)) // 1) * 10


def route_key(origin: Code, destination: Code) -> str:
    """A route as its seeded values name it: "RUH-LHR"."""
    return f"{origin}-{destination}"


def deal_day(origin: Code, destination: Code, day: date) -> bool:
    """Whether `day` is a deal day of the route: every flight of it that day a fifth cheaper."""
    return h("deal", route_key(origin, destination), day.isoformat()) % 13 == 0


def _season(day: date) -> Fraction:
    for first, last, factor in SEASONS:
        if first <= day <= last:
            return factor
    return Fraction(1)


def economy_fare(departure: Departure) -> int:
    """The flight's economy fare on its date, one way, per person."""
    flight, day = departure.flight, departure.day
    other = flight.destination if flight.origin == HOME else flight.origin
    value = BASE[other] * WEEKDAY[day.weekday()] * _season(day)
    if flight.departs.hour < 6:
        value *= EARLY
    if deal_day(flight.origin, flight.destination, day):
        value *= DEAL
    value *= JITTER[h("jitter", str(flight.number), day.isoformat()) % 3]
    return round10(value)


def fare(departure: Departure, cabin: Cabin) -> int | None:
    """The flight's fare in `cabin` on its date, one way, per person, or `None` when the cabin is
    not sold on its aircraft."""
    if cabin not in departure.flight.cabins:
        return None
    economy = economy_fare(departure)
    return economy if cabin == "economy" else round10(economy * CABIN_FACTOR[cabin])


def seats_left(flight: Flight, day: date, cabin: Cabin) -> int:
    """The seats left in `cabin` on `flight` that day; 0 when sold out or not sold."""
    if cabin not in flight.cabins:
        return 0
    n = h("seats", str(flight.number), day.isoformat(), cabin)
    if cabin == "economy":
        return 0 if n % 41 == 0 else 4 + n % 57
    return n % 9 if cabin == "business" else n % 5


@dataclass(frozen=True)
class FareDay:
    """One day of the fare calendar: its cheapest fare in a cabin, or `None` with no flight."""

    day: date
    fare: int | None


def calendar(
    origin: Code, destination: Code, first: date, last: date, cabin: Cabin = "economy"
) -> tuple[FareDay, ...]:
    """Each day from `first` to `last`, both kept, with its cheapest fare in `cabin` (its
    cheapest flight's); a day with no flight selling it is `None`, never a made-up fare."""
    days = []
    day = first
    while day <= last:
        sold = (fare(d, cabin) for d in departures(origin, destination, day))
        fares = [f for f in sold if f is not None]
        days.append(FareDay(day, min(fares) if fares else None))
        day += timedelta(days=1)
    return tuple(days)
