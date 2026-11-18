"""SerpApi's Google Flights answer read into one day's offers (pure, no IO): `read_day`.

The answer is read leniently (fields it does not need are ignored). A body that is not JSON or
not the answer's shape, or whose currency is not SAR, is `bad_answer`; `search_metadata.status`
"Error" is `http_error`. The itineraries are `best_flights` then `other_flights`; each becomes an
`Offer`, or is dropped (and logged, by reason alone) when a flight number is not a carrier code
and a number, a time or an airport cannot be read, it has no whole-number price, or it has more
than three flights. Offers sharing an id keep the cheaper; they come in departure order. No
itinerary at all is `no_flights` (SerpApi's "hasn't returned any results" included); itineraries
none of which could be read are `bad_answer`, never no flights.

The carrier is the flight number's prefix (carriers.py), `airplane` "Bus" marks a road leg, and
`plane_and_crew_by` names the carrier that flies it. The provider's city names of the airports
it answered with (`airports[]`) become `DayOffers.cities`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from t2_agentic_voice import get_logger

from flight_voice.flight_data.carriers import by_name, carrier
from flight_voice.flight_data.model import Layover, Money, Offer, Segment, offer_id
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayOffers, OfferQuery

__all__ = ["Read", "read_day"]

log = get_logger(__name__)

_NUMBER: Final = re.compile(r"^([A-Z0-9]{2})\s*(\d{1,4}[A-Z]?)$")
_IATA: Final = re.compile(r"^[A-Z]{3}$")
_TIME: Final = "%Y-%m-%d %H:%M"
_MOST_SEGMENTS: Final = 3


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)


class _Metadata(_Raw):
    status: str | None = None
    total_time_taken: float | None = None


class _Parameters(_Raw):
    currency: str | None = None


class _Body(_Raw):
    search_metadata: _Metadata = Field(default_factory=_Metadata)
    search_parameters: _Parameters = Field(default_factory=_Parameters)
    best_flights: list[JsonValue] = []
    other_flights: list[JsonValue] = []
    airports: list[JsonValue] = []


class _Stop(_Raw):
    id: str
    time: str
    name: str | None = None


class _Flight(_Raw):
    departure_airport: _Stop
    arrival_airport: _Stop
    duration: int
    flight_number: str
    airline: str | None = None
    airplane: str | None = None
    plane_and_crew_by: str | None = None


class _Wait(_Raw):
    id: str
    duration: int
    name: str | None = None
    overnight: bool = False


class _Itinerary(_Raw):
    flights: list[_Flight] = Field(min_length=1)
    layovers: list[_Wait] = []
    total_duration: int | None = None
    price: JsonValue = None


class _Named(_Raw):
    id: str


class _CityOf(_Raw):
    airport: _Named
    city: str | None = None


class _Leg(_Raw):
    departure: list[_CityOf] = []
    arrival: list[_CityOf] = []


class Read(BaseModel):
    """What one answer held: the day's offers, and SerpApi's own seconds for the search."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: DayOffers
    took_s: float | None = None


def read_day(content: bytes, q: OfferQuery, fetched_at: datetime) -> Read:
    """The offers of `content`, SerpApi's answer to `q` (the module's docstring);
    FlightDataUnavailableError when it cannot be read or says it failed."""
    try:
        body = _Body.model_validate_json(content)
    except ValidationError:
        body = None
    if body is None:  # raised here, outside the handler: no chain to the body
        raise FlightDataUnavailableError("day", "bad_answer")
    if body.search_metadata.status == "Error":
        raise FlightDataUnavailableError("day", "http_error")
    if body.search_parameters.currency != "SAR":
        raise FlightDataUnavailableError("day", "bad_answer")
    raw = [*body.best_flights, *body.other_flights]
    offers: dict[str, Offer] = {}
    for each in raw:
        offer = _offer(each, q, fetched_at)
        if offer is not None and (offer.id not in offers or _cheaper(offer, offers[offer.id])):
            offers[offer.id] = offer
    if raw and not offers:
        raise FlightDataUnavailableError("day", "bad_answer")
    ordered = tuple(sorted(offers.values(), key=lambda o: (o.departs, o.id)))
    answer = DayOffers(
        query=q,
        status="ok" if ordered else "no_flights",
        offers=ordered,
        cities=_cities(body.airports),
        fetched_at=fetched_at,
    )
    return Read(answer=answer, took_s=body.search_metadata.total_time_taken)


def _cheaper(offer: Offer, than: Offer) -> bool:
    return offer.price.amount < than.price.amount


def _dropped(reason: str) -> None:
    log.info("flight_data_itinerary_dropped", reason=reason)


def _offer(raw: JsonValue, q: OfferQuery, fetched_at: datetime) -> Offer | None:
    """One itinerary as an offer, or None (logged) when it cannot be one."""
    try:
        itinerary = _Itinerary.model_validate(raw)
    except ValidationError:
        _dropped("shape")
        return None
    price = itinerary.price
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        _dropped("no_price")
        return None
    if len(itinerary.flights) > _MOST_SEGMENTS:
        _dropped("too_many_flights")
        return None
    try:
        segments = tuple(_segment(f) for f in itinerary.flights)
        layovers = tuple(
            Layover(airport=w.id, minutes=w.duration, overnight=w.overnight, name=w.name)
            for w in itinerary.layovers
        )
        minutes = itinerary.total_duration or sum(s.minutes for s in segments) + sum(
            w.minutes for w in layovers
        )
        return Offer(
            id=offer_id(segments),
            segments=segments,
            layovers=layovers,
            minutes=minutes,
            cabin=q.cabin,
            adults=q.adults,
            price=Money(amount=price),
            fetched_at=fetched_at,
        )
    except (ValueError, ValidationError):  # pydantic's error is a ValueError too
        _dropped("flight")
        return None


def _segment(flight: _Flight) -> Segment:
    """One flight as a segment; ValueError when its number, times or airports cannot be read."""
    number = _NUMBER.match(flight.flight_number.strip())
    if number is None:
        raise ValueError("a flight number is a carrier code and a number")
    marketing = carrier(number.group(1), flight.airline)
    operator = by_name(flight.plane_and_crew_by) if flight.plane_and_crew_by else None
    airplane = (flight.airplane or "").strip()
    return Segment(
        carrier=marketing,
        number=number.group(2),
        origin=flight.departure_airport.id,
        destination=flight.arrival_airport.id,
        departs=datetime.strptime(flight.departure_airport.time, _TIME),
        arrives=datetime.strptime(flight.arrival_airport.time, _TIME),
        minutes=flight.duration,
        aircraft=airplane or None,
        bus=airplane.lower() == "bus",
        operated_by=operator if operator is not None and operator != marketing else None,
    )


def _cities(airports: list[JsonValue]) -> tuple[tuple[str, str], ...]:
    """The provider's city of each airport it answered with, each airport once, in order."""
    found: dict[str, str] = {}
    for raw in airports:
        try:
            leg = _Leg.model_validate(raw)
        except ValidationError:
            continue
        for each in (*leg.departure, *leg.arrival):
            code, name = each.airport.id, (each.city or "").strip()
            if _IATA.match(code) and name:
                found.setdefault(code, name)
    return tuple(found.items())
