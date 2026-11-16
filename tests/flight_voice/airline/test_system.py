"""The mock airline's facade: the demo traveler and the counts worked out for them, the reads by
their modes (a failure raised, never an empty answer), and the profile scoped to the traveler
ID it is given."""

from __future__ import annotations

import asyncio
import time
from datetime import date

import pytest
from flight_voice.airline.bookings import BookingStore, Leg, NewBooking
from flight_voice.airline.profile import PAST_TRIPS, TRAVELER, CityCount, insights
from flight_voice.airline.system import (
    PROFILE_MODES,
    SEARCH_MODES,
    Airline,
    AirlineUnavailableError,
    ProfileMode,
    SearchMode,
    live_today,
)

TODAY = date(2026, 11, 16)


def _airline(search_mode: SearchMode = "answer", profile_mode: ProfileMode = "answer") -> Airline:
    return Airline(
        today=lambda: TODAY, search_mode=search_mode, profile_mode=profile_mode, slow_s=0.2
    )


def test_the_demo_traveler() -> None:
    assert (TRAVELER.id, TRAVELER.first_en, TRAVELER.first_ar) == ("T-0001", "Khalid", "خالد")
    assert (TRAVELER.tier, TRAVELER.tier_ar, TRAVELER.home) == ("Gold", "ذهبي", "RUH")
    assert TRAVELER.preferred_cabin == "economy"
    assert all(t.depart < TODAY for t in PAST_TRIPS)


def test_the_counts_are_worked_out_in_code() -> None:
    counts = insights(PAST_TRIPS)
    assert counts.trips == 5 and counts.most_visited == "DXB"
    assert counts.cabin_most_used == "economy"
    assert counts.by_city == (
        CityCount(city="DXB", trips=2, last_depart=date(2026, 10, 8)),
        CityCount(city="LHR", trips=1, last_depart=date(2026, 9, 3)),
        CityCount(city="JED", trips=1, last_depart=date(2026, 8, 20)),
        CityCount(city="CAI", trips=1, last_depart=date(2026, 6, 12)),
    )
    empty = insights(())
    assert (empty.trips, empty.by_city, empty.most_visited, empty.cabin_most_used) == (
        0,
        (),
        None,
        None,
    )


def test_a_tie_goes_to_the_one_flown_last() -> None:
    london, cairo = PAST_TRIPS[1], PAST_TRIPS[3]  # business 2026-09, economy 2026-06
    counts = insights((cairo, london))
    assert counts.most_visited == "LHR" and counts.cabin_most_used == "business"


def test_the_profile_holds_the_trips_flown_and_the_bookings_made() -> None:
    airline = _airline()
    new = NewBooking(
        request_id="req-1",
        traveler_id=TRAVELER.id,
        legs=(Leg(flight=401, day=date(2026, 12, 17)),),
        cabin="economy",
        travelers=1,
        total_sar=3560,
    )
    made = asyncio.run(airline.bookings.create(new))
    profile = asyncio.run(airline.profile(TRAVELER.id))
    assert profile is not None and profile.traveler == TRAVELER
    assert [b.reference for b in profile.flown] == [t.reference for t in PAST_TRIPS]
    assert profile.booked == (made,)
    assert profile.insights == insights(PAST_TRIPS)  # a booking made is not a trip flown


def test_the_profile_answers_only_for_a_known_traveler() -> None:
    assert asyncio.run(_airline().profile("T-0002")) is None
    assert asyncio.run(_airline().profile("")) is None


def test_a_failing_profile_raises_never_an_empty_one() -> None:
    with pytest.raises(AirlineUnavailableError) as failed:
        asyncio.run(_airline(profile_mode="fail").profile(TRAVELER.id))
    assert failed.value.details == {"read": "profile"}
    assert set(PROFILE_MODES) == {"answer", "fail"}


def test_a_failing_search_raises_for_every_read() -> None:
    airline = _airline(search_mode="fail")
    for read in (
        airline.departures("RUH", "LHR", date(2026, 12, 17)),
        airline.calendar("RUH", "IST", date(2027, 1, 1), date(2027, 1, 7)),
    ):
        with pytest.raises(AirlineUnavailableError) as failed:
            asyncio.run(read)
        assert failed.value.details == {"read": "search"}
    assert set(SEARCH_MODES) == {"answer", "fail", "slow"}


def test_a_slow_search_answers_after_its_wait() -> None:
    started = time.monotonic()
    flights = asyncio.run(_airline(search_mode="slow").departures("RUH", "LHR", date(2026, 12, 17)))
    assert time.monotonic() - started >= 0.2
    assert [d.flight.number for d in flights] == [401, 403]
    days = asyncio.run(_airline().calendar("RUH", "IST", date(2027, 1, 1), date(2027, 1, 3)))
    assert [d.fare for d in days] == [1920, 1730, 1700]


def test_a_slow_search_waits_once_for_a_trips_two_days() -> None:
    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    slow = Airline(today=lambda: TODAY, search_mode="slow", slow_s=4.0, sleep=wait)
    outs, backs = asyncio.run(
        slow.trip_departures("RUH", "LHR", date(2026, 12, 17), date(2026, 12, 20))
    )
    assert [d.flight.number for d in outs] == [401, 403]
    assert [d.flight.number for d in backs] == [402, 404]
    assert waits == [4.0]
    one_way = asyncio.run(slow.trip_departures("RUH", "LHR", date(2026, 12, 17), None))
    assert one_way[1] == () and waits == [4.0, 4.0]


def test_today_is_the_airlines_clock() -> None:
    assert _airline().today() == TODAY
    store = BookingStore(today=lambda: TODAY)
    assert Airline(today=lambda: TODAY, bookings=store).bookings is store
    assert abs((live_today() - date.today()).days) <= 1
