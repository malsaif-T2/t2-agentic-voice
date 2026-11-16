"""The mock airline as the tools and the booking action reach it (`Airline`): today in Riyadh,
the flights of a day, the fare calendar, the traveler's profile, and the bookings store.

Its reads answer by their modes, set by the settings or a scripted call: `search_mode` for the
flights, the calendar and the cabins (`answer`; `fail`, which raises `AirlineUnavailableError`;
`slow`, which answers after `slow_s`, so a call's progress line plays), and `profile_mode` for
the profile (`answer`, `fail`). Each tool turns `AirlineUnavailableError` into a failure it
says, never into "nothing found". The profile answers only for the traveler ID it is given.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict

from flight_voice.airline import fares, schedule
from flight_voice.airline.airports import Code
from flight_voice.airline.bookings import AirlineError, Booking, BookingStore
from flight_voice.airline.dates import RIYADH, riyadh_today
from flight_voice.airline.profile import TRAVELER, Insights, Traveler, insights

SearchMode = Literal["answer", "fail", "slow"]
SEARCH_MODES: Final[tuple[SearchMode, ...]] = get_args(SearchMode)
ProfileMode = Literal["answer", "fail"]
PROFILE_MODES: Final[tuple[ProfileMode, ...]] = get_args(ProfileMode)
SLOW_S: Final = 4.0
# The travelers the airline knows, by ID: the demo traveler alone.
TRAVELERS: Final[dict[str, Traveler]] = {TRAVELER.id: TRAVELER}


class AirlineUnavailableError(AirlineError):
    """A read of the airline did not answer: nothing is known, so nothing may be said found."""

    code = "airline_unavailable"

    def __init__(self, read: Literal["search", "profile"]) -> None:
        super().__init__("The airline did not answer.", details={"read": read})


def live_today() -> date:
    """Today's date in Riyadh, now."""
    return riyadh_today(datetime.now(RIYADH))


class Profile(BaseModel):
    """A traveler's profile: who they are, the trips they flew (newest first), the bookings
    made since (newest first) and the counts of the trips flown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    traveler: Traveler
    flown: tuple[Booking, ...]
    booked: tuple[Booking, ...]
    insights: Insights


class Airline:
    """The mock airline, today being `today()`, its bookings in `bookings` (a new store when
    none is given), its reads answered by their modes, a slow read taking `slow_s`."""

    def __init__(
        self,
        *,
        today: Callable[[], date] = live_today,
        bookings: BookingStore | None = None,
        search_mode: SearchMode = "answer",
        profile_mode: ProfileMode = "answer",
        slow_s: float = SLOW_S,
    ) -> None:
        self._today = today
        self.bookings = bookings if bookings is not None else BookingStore(today=today)
        self.search_mode: SearchMode = search_mode
        self.profile_mode: ProfileMode = profile_mode
        self.slow_s = slow_s

    def today(self) -> date:
        """Today in Riyadh, as the airline counts it."""
        return self._today()

    async def departures(
        self, origin: Code, destination: Code, day: date
    ) -> tuple[schedule.Departure, ...]:
        """The route's flights on `day`, as the search mode says."""
        await self._search()
        return schedule.departures(origin, destination, day)

    async def calendar(
        self, origin: Code, destination: Code, first: date, last: date
    ) -> tuple[fares.FareDay, ...]:
        """Each day's cheapest economy fare from `first` to `last`, as the search mode says."""
        await self._search()
        return fares.calendar(origin, destination, first, last)

    async def profile(self, traveler_id: str) -> Profile | None:
        """The profile of `traveler_id`, or `None` for a traveler the airline does not know, as
        the profile mode says."""
        if self.profile_mode == "fail":
            raise AirlineUnavailableError("profile")
        traveler = TRAVELERS.get(traveler_id)
        if traveler is None:
            return None
        listed = self.bookings.listed(traveler_id)
        flown = tuple(b for b in listed if b.flown)
        return Profile(
            traveler=traveler,
            flown=flown,
            booked=tuple(b for b in listed if not b.flown),
            insights=insights(flown),
        )

    async def _search(self) -> None:
        if self.search_mode == "fail":
            raise AirlineUnavailableError("search")
        if self.search_mode == "slow":
            await asyncio.sleep(self.slow_s)
