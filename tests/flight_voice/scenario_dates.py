"""Finds, from the mock airline itself, the days scripted calls need: a deal day, a flight whose
business cabin is sold out, a Singapore Tuesday. A scripted call names its date; the finder's
test (`airline/test_fares.py`) holds that each pinned date still has its property, so a change
to the fare or seat formula fails there, loudly, rather than in a call."""

from __future__ import annotations

from datetime import date, timedelta

from flight_voice.airline.airports import Code
from flight_voice.airline.fares import deal_day, seats_left
from flight_voice.airline.schedule import departures, flies_on, window

# The day runs and tests pin as today: Monday 2026-11-16.
TODAY = date(2026, 11, 16)


def _days(after: date) -> list[date]:
    first, last = window(TODAY)
    start = max(first, after)
    return [start + timedelta(days=n) for n in range((last - start).days + 1)]


def first_deal_day(origin: Code, destination: Code, after: date = TODAY) -> date | None:
    """The first deal day of the route on or after `after`, inside the pinned window."""
    return next((d for d in _days(after) if deal_day(origin, destination, d)), None)


def business_sold_out(
    origin: Code, destination: Code, after: date = TODAY
) -> tuple[int, date] | None:
    """The first flight and day of the route, on or after `after`, whose business cabin has no
    seat left while its economy cabin has some."""
    for day in _days(after):
        for d in departures(origin, destination, day):
            business = seats_left(d.flight, day, "business")
            if business == 0 and seats_left(d.flight, day, "economy") > 0:
                return d.flight.number, day
    return None


def no_flight_day(origin: Code, destination: Code, after: date = TODAY) -> date | None:
    """The first day of the route, on or after `after`, with no flight."""
    return next((d for d in _days(after) if not flies_on(origin, destination, d)), None)
