"""The flight agent's read tools, each over the mock airline and the call's trip draft: what each
gives the talker (`results.py`), the card it shows (`cards.py`), and the tools themselves, all
seven of them from `flight_tools`."""

from __future__ import annotations

from t2_agentic_voice import Tool

from flight_voice.airline.system import Airline
from flight_voice.tools.cabins import compare_cabins
from flight_voice.tools.calendar import fare_calendar
from flight_voice.tools.choose import change_trip, choose_flight
from flight_voice.tools.profile import traveler_profile
from flight_voice.tools.search import search_flights
from flight_voice.tools.trip_view import get_trip
from flight_voice.trip import TripBook


def flight_tools(airline: Airline, trips: TripBook) -> tuple[Tool, ...]:
    """The read tools over `airline`, each writing or reading the call's draft in `trips`: the
    search, the pick, the change, the trip, the fare calendar, the cabins and the profile."""
    return (
        search_flights(airline, trips),
        choose_flight(airline, trips),
        change_trip(airline, trips),
        get_trip(airline, trips),
        fare_calendar(airline, trips),
        compare_cabins(airline, trips),
        traveler_profile(airline),
    )
