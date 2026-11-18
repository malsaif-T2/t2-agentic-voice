"""What the lean tools run over (`LeanDeps`): the flight source and the places a caller may
name, today, the mock airline (its bookings and the traveler's profile), each call's trip and
its booking check, and the network they are on.

On the mock network (`mock_deps`) the source is the mock airline behind the port, its places
the mock's ten airports, its flights carrying the airline's code and names, and `book_trip` is
registered. On the real network (plan 011's block B) the source is a flight data provider and
`bookable` is false: `book_trip` is not registered, the instructions end a trip's summary with
the airline's own site, and the vocabulary and pronunciation are the real network's (`terms`
replacing persona.py's, `pronounce` added to the airline's code).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

from flight_voice.airline.system import Airline
from flight_voice.flight_data.logged import Logged
from flight_voice.flight_data.mock import MockFlightData, MockPlaces
from flight_voice.flight_data.model import Carrier
from flight_voice.flight_data.port import FlightData, Places
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.draft import LeanBook
from flight_voice.lean.results import Network
from flight_voice.persona import Names

__all__ = ["LeanDeps", "carrier_of", "mock_deps"]


@dataclass(frozen=True)
class LeanDeps:
    """The lean tools' sources and state (the module's docstring)."""

    data: FlightData
    places: Places
    today: Callable[[], date]
    airline: Airline
    trips: LeanBook
    check: BookingCheck
    bookable: bool = True
    network: Network = "mock"
    pronounce: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    terms: tuple[str, ...] | None = None


def carrier_of(names: Names) -> Carrier:
    """The mock airline as a carrier: its code and its names."""
    return Carrier(
        code=names.airline_code, name_en=names.airline_name_en, name_ar=names.airline_name_ar
    )


def mock_deps(
    airline: Airline,
    names: Names,
    *,
    today: Callable[[], date] | None = None,
    trips: LeanBook | None = None,
    check: BookingCheck | None = None,
    logged: bool = False,
) -> LeanDeps:
    """The lean tools over the mock airline (the module's docstring): today the airline's
    unless given, a new trip book and booking check unless given, and the source wrapped in
    `Logged` when `logged` (run F reads what it answered)."""
    places = MockPlaces()
    source = MockFlightData(airline, carrier_of(names))
    data: FlightData = Logged(source) if logged else source
    return LeanDeps(
        data=data,
        places=places,
        today=airline.today if today is None else today,
        airline=airline,
        trips=LeanBook(places.home) if trips is None else trips,
        check=BookingCheck() if check is None else check,
    )
