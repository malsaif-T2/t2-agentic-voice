"""What the lean tools' tests of the real network share: a call over a fake flight source and
directory (tests/flight_voice/flight_data/fake.py) that does not book, and a day of offers from
Riyadh to London with several airlines, a connection by Dubai and one partly by bus."""

from __future__ import annotations

from datetime import date, datetime
from typing import Final

from flight_voice.flight_data.model import Layover, Offer
from flight_voice.lean.booking_check import BookingCheck
from flight_voice.lean.deps import LeanDeps
from flight_voice.lean.draft import LeanBook
from flight_voice.said import Tag

from tests.flight_voice.flight_data.fake import (
    BRITISH,
    DUBAI,
    EMIRATES,
    LONDON,
    QATAR,
    RIYADH,
    SAUDIA,
    FakeFlightData,
    FakePlaces,
    answered,
    nonstop,
    offer,
    query,
    segment,
)
from tests.flight_voice.lean.lean_support import LeanCall
from tests.flight_voice.tools.tool_support import airline

OUT: Final = date(2026, 12, 3)
BACK: Final = date(2026, 12, 10)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute)


def london_day(adults: int = 1, scale: int = 1) -> tuple[Offer, ...]:
    """Riyadh to London on `OUT`: three Saudia nonstops, a British Airways one, Emirates by
    Dubai (cheaper by far) and Qatar by Doha, each price for `adults` times `scale`."""

    def priced(amount: int) -> int:
        return amount * scale

    route = ("RUH", "LHR")
    by_dubai = offer(
        segment(EMIRATES, "818", ("RUH", "DXB"), _at(OUT, 4, 10), 125, aircraft="Boeing 777-300ER"),
        segment(EMIRATES, "3", ("DXB", "LHR"), _at(OUT, 8, 20), 440),
        layovers=(Layover(airport="DXB", minutes=125),),
        price=priced(2480),
        adults=adults,
    )
    by_doha = offer(
        segment(QATAR, "1163", ("RUH", "DOH"), _at(OUT, 2, 0), 90),
        segment(QATAR, "3", ("DOH", "LHR"), _at(OUT, 4, 30), 420),
        layovers=(Layover(airport="DOH", minutes=60),),
        price=priced(2610),
        adults=adults,
    )
    return (
        nonstop(SAUDIA, "119", route, _at(OUT, 1, 40), 445, priced(3150), adults=adults),
        by_doha,
        by_dubai,
        nonstop(BRITISH, "264", route, _at(OUT, 9, 30), 430, priced(3420), adults=adults),
        nonstop(SAUDIA, "105", route, _at(OUT, 14, 0), 445, priced(3300), adults=adults),
        nonstop(SAUDIA, "121", route, _at(OUT, 23, 55), 445, priced(3200), adults=adults),
    )


def london_back(adults: int = 1) -> tuple[Offer, ...]:
    """London to Riyadh on `BACK`: two Saudia nonstops."""
    route = ("LHR", "RUH")
    return (
        nonstop(SAUDIA, "120", route, _at(BACK, 9, 0), 400, 3000 * adults, adults=adults),
        nonstop(SAUDIA, "106", route, _at(BACK, 21, 0), 400, 2900 * adults, adults=adults),
    )


def real_call(data: FakeFlightData | None = None, tag: Tag = "en") -> LeanCall:
    """A call on the real network over `data` (a fake with the London days unless given)."""
    if data is None:
        data = FakeFlightData()
        data.set(answered(query(RIYADH, LONDON, OUT), london_day()))
        data.set(answered(query(LONDON, RIYADH, BACK), london_back()))
    places = FakePlaces()
    deps = LeanDeps(
        data=data,
        places=places,
        today=airline().today,
        airline=airline(),
        trips=LeanBook(places.home),
        check=BookingCheck(),
        bookable=False,
        network="real",
    )
    return LeanCall(tag, deps=deps)


__all__ = ["BACK", "DUBAI", "OUT", "london_back", "london_day", "real_call"]
