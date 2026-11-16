"""The mock airline's timetable: every route out of Riyadh and back, its flights' numbers,
aircraft and local times at each end, Singapore's Tuesday gap, first class only on the 787-9,
and no day sold past the one the fixed offsets hold to."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from flight_voice.airline.airports import CODES, HOME, Code
from flight_voice.airline.schedule import (
    LAST_DAY,
    WINDOW_DAYS,
    OutsideTimetableError,
    departures,
    find_flight,
    flies_on,
    flights,
    route_served,
    window,
)

OTHERS: tuple[Code, ...] = tuple(c for c in CODES if c != HOME)
# Monday 2026-11-16, the day runs and tests pin as today; a Thursday in the winter break.
TODAY = date(2026, 11, 16)
THURSDAY = date(2026, 12, 17)
# How many flights each route flies a day, each way.
PER_DAY = {"JED": 4, "DXB": 3, "DOH": 3, "CAI": 2, "IST": 2, "LHR": 2, "CDG": 2, "BOM": 2, "SIN": 1}


@pytest.mark.parametrize("other", OTHERS)
def test_every_route_flies_both_ways_odd_out_and_even_back(other: Code) -> None:
    out, back = flights(HOME, other), flights(other, HOME)
    assert len(out) == len(back) == PER_DAY[other]
    assert all(f.number % 2 == 1 and (f.origin, f.destination) == (HOME, other) for f in out)
    assert all(f.number % 2 == 0 and (f.origin, f.destination) == (other, HOME) for f in back)
    assert [f.number + 1 for f in out] == [f.number for f in back]
    assert [f.departs for f in out] == sorted(f.departs for f in out)
    assert len(departures(HOME, other, THURSDAY)) == PER_DAY[other]


def test_every_flight_number_is_one_flight() -> None:
    numbers = [f.number for o in OTHERS for f in (*flights(HOME, o), *flights(o, HOME))]
    assert len(numbers) == len(set(numbers)) == 42
    found = find_flight(401)
    assert found is not None and (found.origin, found.destination) == ("RUH", "LHR")
    assert find_flight(999) is None


def test_no_route_between_two_other_cities_nor_to_itself() -> None:
    assert not route_served("JED", "DXB") and flights("JED", "DXB") == ()
    assert not route_served("RUH", "RUH") and not flies_on("JED", "DXB", THURSDAY)
    assert departures("JED", "DXB", THURSDAY) == ()
    assert all(route_served(HOME, o) and route_served(o, HOME) for o in OTHERS)


def test_london_lands_in_londons_time() -> None:
    """RUH 09:10 (UTC+3) plus 7 h 05 lands at Heathrow 13:15 (UTC+0) the same day."""
    first = departures("RUH", "LHR", THURSDAY)[0]
    assert first.flight.number == 401 and first.flight.aircraft == "787-9"
    assert first.departs_at == datetime(2026, 12, 17, 9, 10, tzinfo=timezone(timedelta(hours=3)))
    assert first.arrives_at == datetime(2026, 12, 17, 13, 15, tzinfo=timezone(timedelta(0)))
    assert first.arrives_at.time() == time(13, 15) and not first.next_day


@pytest.mark.parametrize(
    ("origin", "destination", "number", "lands", "next_day"),
    [
        ("LHR", "RUH", 402, "01:20", True),  # 16:00 UTC + 6h20 = 22:20 UTC, 01:20 in Riyadh
        ("RUH", "SIN", 601, "11:25", True),  # 22:05 +3, + 8h20 = 03:25 UTC, 11:25 at +8
        ("SIN", "RUH", 602, "12:50", False),  # 08:40 +8, + 9h10 = 09:50 UTC, 12:50 at +3
        ("RUH", "CDG", 451, "06:30", False),  # 01:55 +3, + 6h35 = 05:30 UTC, 06:30 at +1
        ("RUH", "BOM", 501, "09:50", False),  # 03:20 +3, + 4h00 = 04:20 UTC, 09:50 at +5:30
        ("RUH", "CAI", 301, "11:15", False),  # 09:30 +3, + 2h45 = 09:15 UTC, 11:15 at +2
        ("DXB", "RUH", 206, "00:55", True),  # 23:55 +4, + 2h00 = 21:55 UTC, 00:55 at +3
    ],
)
def test_each_arrival_is_in_the_arrival_airports_time(
    origin: Code, destination: Code, number: int, lands: str, next_day: bool
) -> None:
    flight = next(d for d in departures(origin, destination, THURSDAY) if d.flight.number == number)
    assert flight.arrives_at.strftime("%H:%M") == lands
    assert flight.next_day is next_day


def test_singapore_has_no_flight_either_way_on_tuesdays() -> None:
    tuesday = date(2026, 11, 17)
    assert tuesday.weekday() == 1
    assert departures("RUH", "SIN", tuesday) == departures("SIN", "RUH", tuesday) == ()
    assert not flies_on("RUH", "SIN", tuesday)
    assert len(departures("RUH", "SIN", tuesday + timedelta(days=1))) == 1
    assert len(departures("RUH", "LHR", tuesday)) == 2


def test_first_class_only_on_the_787() -> None:
    for other in OTHERS:
        for flight in (*flights(HOME, other), *flights(other, HOME)):
            wide = other in ("LHR", "CDG", "SIN")
            assert (flight.aircraft == "787-9") is wide
            assert flight.cabins == (
                ("economy", "business", "first") if wide else ("economy", "business")
            )


def test_the_window_is_120_days_but_never_past_the_fixed_offsets() -> None:
    assert window(TODAY) == (TODAY, date(2027, 3, 16)) and WINDOW_DAYS == 120
    later = date(2027, 1, 10)
    assert window(later) == (later, LAST_DAY) == (later, date(2027, 3, 27))


def test_no_day_past_the_fixed_offsets_is_flown() -> None:
    """Europe's summer time begins on 2027-03-28; a fixed offset would put London's and Paris's
    times an hour wrong from then, so the timetable stops the day before."""
    assert len(departures("RUH", "LHR", LAST_DAY)) == 2
    routes: tuple[tuple[Code, Code], ...] = (("RUH", "LHR"), ("CDG", "RUH"), ("RUH", "CAI"))
    for origin, destination in routes:
        with pytest.raises(OutsideTimetableError, match="2027-03-27"):
            departures(origin, destination, LAST_DAY + timedelta(days=1))
