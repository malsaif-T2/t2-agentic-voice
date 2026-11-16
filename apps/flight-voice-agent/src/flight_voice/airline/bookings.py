"""The mock airline's bookings, kept in memory and seeded with the demo traveler's five past
trips; `reset()` puts it back to the seed, and nothing is written to disk.

- **A booking is priced again at the write** (`create`): each leg's flight must fly that day,
  not before today, with seats for every traveler in the cabin, and the legs' fares times the
  travelers must be the total the read-back said; else `BookingRefused`, and nothing is booked.
  So the price read back is the price booked, or nothing is.
- **The request ID is the idempotency key:** a write sent again with it returns the booking it
  made, never a second one; every write that reaches the store is logged (`writes`), so a test
  sees how many were sent.
- **A new reference** is six digits from the seeded number of the request ID, never one held.
- **Modes**, as Ole5's mock ticket system has them: `answer`; `refuse`, which raises
  `BookingRefused` and changes nothing; `timeout`, which waits `late_s` and raises
  `BookingTimeoutError`, having done nothing; `late`, which books at once and answers only after
  `late_s`, so a lookup in the meantime finds it. `late_s` (30 s) is above an action's 20 s.
- **The lookup** (`find`) by request ID can be switched off (`LookupUnavailableError`).
- **Scoped by traveler:** `find` and `listed` answer only for the traveler ID they are given.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice import T2VoiceError, get_logger

from flight_voice.airline.fares import fare, h, seats_left
from flight_voice.airline.profile import PAST_TRIPS, TRAVELER, Trip
from flight_voice.airline.schedule import (
    LAST_DAY,
    Cabin,
    Flight,
    departure,
    find_flight,
    flies_on,
    flights,
)

Mode = Literal["answer", "refuse", "timeout", "late"]
MODES: Final[tuple[Mode, ...]] = get_args(Mode)
LATE_S: Final = 30.0
RefusalReason = Literal["refused", "price_changed", "no_seats", "date_passed", "no_such_flight"]
_REFUSALS: Final[dict[RefusalReason, str]] = {
    "refused": "The booking system refused the request.",
    "price_changed": "The fare is no longer the one read back.",
    "no_seats": "A flight has too few seats left in the cabin.",
    "date_passed": "A flight's day has passed.",
    "no_such_flight": "A flight does not fly that route on that day.",
}

log = get_logger(__name__)


class AirlineError(T2VoiceError):
    """A failure of the mock airline; its message holds no value of the request."""

    code = "airline_error"


class BookingRefused(AirlineError):  # noqa: N818 - a refusal, as ActionRejected is
    """The booking system refused the write, for `reason`: definitely nothing booked."""

    code = "booking_refused"

    def __init__(self, reason: RefusalReason) -> None:
        super().__init__(_REFUSALS[reason], details={"reason": reason})
        self.reason: RefusalReason = reason


class BookingTimeoutError(AirlineError):
    """The booking system did not answer in time: the write may or may not have been made."""

    code = "booking_timeout"

    def __init__(self) -> None:
        super().__init__("The booking system did not answer in time.")


class LookupUnavailableError(AirlineError):
    """`find` was called while the lookup by request ID is off."""

    code = "lookup_unavailable"

    def __init__(self) -> None:
        super().__init__("The booking system cannot look a write up by its request ID.")


class Leg(BaseModel):
    """One flight of a booking, on its day."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    flight: int
    day: date


class NewBooking(BaseModel):
    """A write: its request ID, whose trip it is, the legs (out, and back for a round trip),
    the cabin, the travelers and the total the read-back said."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    traveler_id: str
    legs: tuple[Leg] | tuple[Leg, Leg]
    cabin: Cabin
    travelers: int = Field(ge=1, le=9)
    total_sar: int = Field(ge=0)


class Booking(Trip):
    """A booking the store holds: the trip, whose it is, its legs, the write that made it
    (none for a seeded past trip) and whether it was flown before today."""

    traveler_id: str
    legs: tuple[Leg, ...]
    request_id: str | None = None
    flown: bool = False


def _seeded(trip: Trip) -> Booking:
    out = flights(trip.origin, trip.destination)[0].number
    legs = [Leg(flight=out, day=trip.depart)]
    if trip.return_date is not None:
        back = flights(trip.destination, trip.origin)[0].number
        legs.append(Leg(flight=back, day=trip.return_date))
    return Booking(**trip.model_dump(), traveler_id=TRAVELER.id, legs=tuple(legs), flown=True)


SEED: Final = tuple(_seeded(t) for t in PAST_TRIPS)


def priced(legs: tuple[Leg, ...], cabin: Cabin, travelers: int, today: date) -> int:
    """The total of `legs` in `cabin` for `travelers`, priced now; `BookingRefused` when a leg
    does not fly, has passed or is short of seats."""
    total = 0
    for leg in legs:
        flight = find_flight(leg.flight)
        if flight is None or leg.day > LAST_DAY:
            raise BookingRefused("no_such_flight")
        if not flies_on(flight.origin, flight.destination, leg.day):
            raise BookingRefused("no_such_flight")
        if leg.day < today:
            raise BookingRefused("date_passed")
        one = fare(departure(flight, leg.day), cabin)
        if one is None or seats_left(flight, leg.day, cabin) < travelers:
            raise BookingRefused("no_seats")
        total += one * travelers
    return total


def _trip_of(legs: tuple[Leg, ...]) -> Flight:
    """The outbound flight of `legs`, once each leg is checked to be one trip: a return flies
    the outbound's route back, on its day or later; `BookingRefused` otherwise."""
    flown = [find_flight(leg.flight) for leg in legs]
    out = flown[0]
    if out is None or None in flown:
        raise BookingRefused("no_such_flight")
    if len(legs) == 2:
        back = flown[1]
        returns = back is not None and (back.origin, back.destination) == (
            out.destination,
            out.origin,
        )
        if not returns or legs[1].day < legs[0].day:
            raise BookingRefused("no_such_flight")
    return out


class BookingStore:
    """The bookings, in memory, its writes answered by `mode`, found by request ID when
    `lookup`, a late or timed-out write taking `late_s`, today being `today()`."""

    def __init__(
        self,
        *,
        today: Callable[[], date],
        mode: Mode = "answer",
        lookup: bool = True,
        late_s: float = LATE_S,
    ) -> None:
        self.mode: Mode = mode
        self.can_find = lookup
        self.late_s = late_s
        self._today = today
        self._made: tuple[Booking, ...] = ()
        self.writes: list[str] = []

    def reset(self) -> None:
        """Back to the seed: every booking made since is dropped, and the write log cleared."""
        self._made = ()
        self.writes = []
        log.info("bookings_reset")

    async def create(self, new: NewBooking) -> Booking:
        """Book `new`, as the mode says (the module's docstring)."""
        mode = self.mode
        self.writes.append(new.request_id)
        if mode == "refuse":
            raise BookingRefused("refused")
        if mode == "timeout":
            log.info("booking_timing_out", seconds=self.late_s)
            await asyncio.sleep(self.late_s)
            raise BookingTimeoutError()
        made = self._book(new)
        log.info("booking_written", mode=mode)
        if mode == "late":
            await asyncio.sleep(self.late_s)
        return made

    def _book(self, new: NewBooking) -> Booking:
        for kept in self._made:
            if kept.request_id == new.request_id:
                if kept.traveler_id != new.traveler_id:
                    raise BookingRefused("refused")
                return kept
        total = priced(new.legs, new.cabin, new.travelers, self._today())
        out = _trip_of(new.legs)
        if total != new.total_sar:
            raise BookingRefused("price_changed")
        made = Booking(
            reference=self._reference(new.request_id),
            origin=out.origin,
            destination=out.destination,
            depart=new.legs[0].day,
            return_date=new.legs[1].day if len(new.legs) == 2 else None,
            travelers=new.travelers,
            cabin=new.cabin,
            total_sar=total,
            traveler_id=new.traveler_id,
            legs=new.legs,
            request_id=new.request_id,
        )
        self._made = (*self._made, made)
        return made

    def _reference(self, request_id: str) -> str:
        held = {b.reference for b in (*SEED, *self._made)}
        attempt = 0
        while True:
            parts = ("ref", request_id) if attempt == 0 else ("ref", request_id, str(attempt))
            reference = str(100_000 + h(*parts) % 900_000)
            if reference not in held:
                return reference
            attempt += 1

    async def find(self, request_id: str, traveler_id: str) -> Booking | None:
        """The booking the write `request_id` made, when it is `traveler_id`'s;
        `LookupUnavailableError` when the lookup is off."""
        if not self.can_find:
            raise LookupUnavailableError()
        return next(
            (b for b in self._made if b.request_id == request_id and b.traveler_id == traveler_id),
            None,
        )

    def listed(self, traveler_id: str) -> tuple[Booking, ...]:
        """Every booking of `traveler_id`, newest first: those made since the seed, the last
        first, then the past trips, the last flown first."""
        made = tuple(b for b in reversed(self._made) if b.traveler_id == traveler_id)
        seeded = tuple(
            sorted((b for b in SEED if b.traveler_id == traveler_id), key=lambda b: b.depart)
        )
        return (*made, *reversed(seeded))
