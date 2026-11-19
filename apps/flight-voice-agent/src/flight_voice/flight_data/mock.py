"""The mock airline (airline/) behind the flight data port: today's T2 Air, exact and
deterministic, so run F and the tests keep the facts they check.

`MockFlightData.day` answers one leg on one day, checking in this order: a place that is not
one of the mock's airports, or a route it does not fly, is `not_served` with the airports it
serves; a cabin the route's aircraft do not carry is `cabin_not_sold` with the cabins they do
(neither reads the airline, so no search mode applies, as today); then one read of the
airline's departures, its fail and slow modes applied once. Each departure that sells the cabin
is an `Offer` of one segment, its local times with their zone dropped (the same HH:MM), its
price the fare times the travelers, its seats the exact count. `days` refuses the same way
before one read of the fare calendar. `nearest` is the scripted search's nearest days with a
flight; `last_day` the booking window's. A span asked `each_day` gives each day's offers too,
from the same exact timetable, after the one read.

`MockPlaces` matches a caller's words as `find_airport` does, over the ten airports.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Final

from flight_voice.airline.airports import AIRPORTS, CODES, HOME, Airport, Code, find_airport
from flight_voice.airline.fares import fare, seats_left
from flight_voice.airline.schedule import (
    CABINS,
    Cabin,
    Departure,
    departures,
    flies_on,
    flights,
    route_served,
    window,
)
from flight_voice.airline.system import Airline, AirlineUnavailableError
from flight_voice.flight_data.model import Carrier, Money, Offer, Place, Segment, offer_id
from flight_voice.flight_data.port import FlightDataUnavailableError, Step
from flight_voice.flight_data.queries import (
    DayFare,
    DayFares,
    DayOffers,
    DayStatus,
    OfferQuery,
    SpanQuery,
)

__all__ = ["NEAREST", "SPAN_DAYS", "MockFlightData", "MockPlaces", "place_of"]

# The longest span searched day by day: two months, as the lean search allows.
SPAN_DAYS: Final = 62
# How many days with a flight `nearest` gives.
NEAREST: Final = 2


def _now() -> datetime:
    return datetime.now(UTC)


def place_of(airport: Airport) -> Place:
    """A mock airport as a place: one airport, its names and aliases."""
    return Place(
        code=airport.code,
        airports=(airport.code,),
        city_en=airport.city_en,
        city_ar=airport.city_ar,
        name_en=airport.name_en,
        name_ar=airport.name_ar,
        aliases=airport.aliases,
    )


def _route(origin: Place, destination: Place) -> tuple[Code, Code] | None:
    """The mock's route between two places, or None when it does not fly it."""
    start = next((c for c in CODES if c == origin.code), None)
    end = next((c for c in CODES if c == destination.code), None)
    if start is None or end is None or not route_served(start, end):
        return None
    return start, end


def _sold(route: tuple[Code, Code]) -> tuple[Cabin, ...]:
    carried = flights(*route)[0].cabins
    return tuple(c for c in CABINS if c in carried)


class MockFlightData:
    """The mock airline as a flight source (the module's docstring): its flights carry
    `carrier`, and each answer is stamped by `clock`."""

    name: Final = "mock"
    span_days: Final = SPAN_DAYS

    def __init__(
        self, airline: Airline, carrier: Carrier, clock: Callable[[], datetime] = _now
    ) -> None:
        self.airline, self.carrier, self._clock = airline, carrier, clock

    def last_day(self, today: date) -> date:
        """The booking window's last day."""
        return window(today)[1]

    async def day(self, q: OfferQuery) -> DayOffers:
        """One leg on one day (the module's docstring)."""
        route = _route(q.origin, q.destination)
        at = self._clock()
        if route is None:
            return DayOffers(query=q, status="not_served", served=CODES, fetched_at=at)
        sold = _sold(route)
        if q.cabin not in sold:
            return DayOffers(query=q, status="cabin_not_sold", cabins=sold, fetched_at=at)
        found = await self._read("day", lambda: self.airline.departures(*route, q.day))
        offers = tuple(self._offer(d, q, at) for d in found if q.cabin in d.flight.cabins)
        status: DayStatus = "ok" if offers else "no_flights"
        return DayOffers(query=q, status=status, offers=offers, fetched_at=at)

    async def days(self, q: SpanQuery) -> DayFares:
        """The lowest price of each day of the span, for all its travelers, from one read of the
        fare calendar (the module's docstring)."""
        route = _route(q.origin, q.destination)
        if route is None:
            return DayFares(query=q, status="not_served", served=CODES)
        sold = _sold(route)
        if q.cabin not in sold:
            return DayFares(query=q, status="cabin_not_sold", cabins=sold)
        found = await self._read(
            "days", lambda: self.airline.calendar(*route, q.first, q.last, q.cabin)
        )
        at = self._clock()

        def offers(day: date) -> tuple[Offer, ...] | None:
            if not q.each_day:
                return None
            flying = departures(*route, day)
            return tuple(
                self._offer(d, q.day(day), at) for d in flying if q.cabin in d.flight.cabins
            )

        days = tuple(
            DayFare(
                day=each.day,
                lowest=None if each.fare is None else Money(amount=each.fare * q.adults),
                flights=sum(q.cabin in d.flight.cabins for d in departures(*route, each.day)),
                offers=offers(each.day),
            )
            for each in found
        )
        times = tuple(f.departs.strftime("%H:%M") for f in flights(*route))
        return DayFares(query=q, status="ok", days=days, times=times)

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        """The `NEAREST` days closest to the query's day, inside the booking window, that the
        route flies, the earlier first of two as close; none on a route it does not fly."""
        route = _route(q.origin, q.destination)
        if route is None:
            return ()
        first, last = window(today)
        found: list[date] = []
        for step in range(1, (last - first).days + 1):
            for near in (q.day - timedelta(days=step), q.day + timedelta(days=step)):
                if first <= near <= last and flies_on(*route, near):
                    found.append(near)
            if len(found) >= NEAREST:
                break
        return tuple(sorted(found[:NEAREST]))

    async def aclose(self) -> None:
        """Nothing to release."""

    async def _read[T](self, step: Step, read: Callable[[], Awaitable[T]]) -> T:
        try:
            return await read()
        except AirlineUnavailableError:
            raise FlightDataUnavailableError(step, "mode_fail") from None

    def _offer(self, departure: Departure, q: OfferQuery, at: datetime) -> Offer:
        flight = departure.flight
        segment = Segment(
            carrier=self.carrier,
            number=str(flight.number),
            origin=flight.origin,
            destination=flight.destination,
            departs=departure.departs_at.replace(tzinfo=None),
            arrives=departure.arrives_at.replace(tzinfo=None),
            minutes=int(flight.duration.total_seconds()) // 60,
            aircraft=flight.aircraft,
        )
        one = fare(departure, q.cabin) or 0  # `day` keeps the departures that sell the cabin
        return Offer(
            id=offer_id((segment,)),
            segments=(segment,),
            minutes=segment.minutes,
            cabin=q.cabin,
            adults=q.adults,
            price=Money(amount=one * q.adults),
            seats_left=seats_left(flight, departure.day, q.cabin),
            fetched_at=at,
        )


class MockPlaces:
    """The mock's ten airports as the places a caller may name, Riyadh the home."""

    served: Final[tuple[Code, ...]] = CODES

    @property
    def home(self) -> Place:
        return place_of(AIRPORTS[HOME])

    def find(self, said: str) -> Place | None:
        """The airport `said` names, as `find_airport` reads it, or None."""
        found = find_airport(said)
        return None if found is None else place_of(found)

    def get(self, code: str) -> Place | None:
        """The airport of `code`, or None when the mock has none."""
        found = next((c for c in CODES if c == code), None)
        return None if found is None else place_of(AIRPORTS[found])
