"""What the booking's tests share: the mock airline on the pinned day, a trip planned to London
(out on Thursday 17 December, back on Sunday the 20th, each leg's first flight chosen), a trip
book that gives that trip to every call (so a `TextCall`, whose call ID is its own, finds it),
and a small agent that speaks Saudi Arabic and English with the booking, and the read tools it
is given, as its tools; its talker judges the answers its lists leave unplaced, as the flight
agent's does."""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from flight_voice.airline.bookings import BookingStore, Leg
from flight_voice.airline.schedule import Cabin, departures
from flight_voice.airline.system import Airline
from flight_voice.booking.action import book_trip
from flight_voice.booking.draft import BookingDraft, filled
from flight_voice.trip import TripBook, TripDraft
from t2_agentic_voice import Action, Caller, Language, Tool, VoiceAgent

from tests.flight_voice.scenario_dates import TODAY

DEC_17: Final = date(2026, 12, 17)
DEC_20: Final = date(2026, 12, 20)
# The demo traveler, as the token route mints every caller; a traveler the airline does not
# know; and a caller who is no traveler at all.
CALLER: Final = Caller(subject="owner", attributes={"traveler_id": "T-0001"})
STRANGER: Final = Caller(subject="other", attributes={"traveler_id": "T-0002"})
NOBODY: Final = Caller(subject="dev")
# A yes with the closing question's send word, said once the question has ended.
YES: Final = {"ar-SA": "إي احجزها", "en": "yes, book it"}
# The caller asking for the trip to be booked, in Saudi Arabic (abi, I want: a Saudi form, so
# the read-back is read in Saudi words) and in English.
REQUEST: Final = {"ar-SA": "أبي تحجز لي الرحلة", "en": "Book the trip for me"}


def airline(**modes: Any) -> Airline:
    """The mock airline, today the pinned Monday, its bookings' modes as given."""
    bookings = BookingStore(today=lambda: TODAY, **modes)
    return Airline(today=lambda: TODAY, bookings=bookings)


def london(*, one_way: bool = False, travelers: int = 1, cabin: Cabin = "economy") -> TripDraft:
    """The trip to London, each leg's first flight of its day chosen."""
    out = departures("RUH", "LHR", DEC_17)[0]
    back = departures("LHR", "RUH", DEC_20)[0]
    return TripDraft(
        destination="LHR",
        depart=DEC_17,
        return_date=None if one_way else DEC_20,
        one_way=one_way,
        travelers=travelers,
        cabin=cabin,
        chosen_outbound=Leg(flight=out.flight.number, day=DEC_17),
        chosen_return=None if one_way else Leg(flight=back.flight.number, day=DEC_20),
    )


def planned(trip: TripDraft | None = None) -> TripBook:
    """A trip book whose every call plans `trip` (London unless given) until a tool puts
    another."""
    kept = london() if trip is None else trip
    return TripBook(start=lambda: kept)


def booking_of(flights: Airline, trip: TripDraft | None = None) -> BookingDraft:
    """The booking `validate` fills from `trip` (London unless given), priced on `flights`."""
    kept = london() if trip is None else trip
    total = kept.total(flights.today())
    assert total is not None
    return filled(kept, total)


def agent(flights: Airline, trips: TripBook, *, tools: tuple[Tool, ...] = ()) -> VoiceAgent:
    """A small agent with the booking over `flights` and `trips`, and `tools` before it."""
    return VoiceAgent(
        name="flight-booking-test",
        languages=[
            Language.saudi_arabic(greeting="هلا، وين حاب تسافر؟"),
            Language.english(greeting="Hi, where would you like to fly?"),
        ],
        instructions="You book flights.",
        tools=[*tools, book_trip(flights, trips)],
        ask_on_unlisted_answers=True,
    )


def booking(made: VoiceAgent) -> Action:
    """The agent's booking action."""
    (found,) = [t for t in made.tools if isinstance(t, Action)]
    return found
