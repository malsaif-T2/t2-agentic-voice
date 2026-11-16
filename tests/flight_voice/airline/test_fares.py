"""The mock airline's fares and seats: exact and the same in every process, each factor as the
formula says, rounded to tens, the calendar's empty days left empty, and the dates scripted calls
pin still holding their properties."""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from fractions import Fraction
from hashlib import sha256

import pytest
from flight_voice.airline.airports import CODES, HOME, Code
from flight_voice.airline.fares import (
    BASE,
    SEED,
    calendar,
    deal_day,
    economy_fare,
    fare,
    h,
    round10,
    seats_left,
)
from flight_voice.airline.schedule import CABINS, Departure, departure, departures, find_flight

from tests.flight_voice.scenario_dates import (
    TODAY,
    business_sold_out,
    first_deal_day,
    no_flight_day,
)
from tests.isolation import child_shell

THURSDAY = date(2026, 12, 17)  # in the winter break


def _on(number: int, day: date) -> Departure:
    flight = find_flight(number)
    assert flight is not None
    return departure(flight, day)


def test_the_seeded_number_is_sha256_of_the_seed_and_parts() -> None:
    assert SEED == "t2air-2026-11"
    assert h("deal", "RUH-LHR", "2026-12-17") == h("deal", "RUH-LHR", "2026-12-17")
    assert h("a", "b") == int(sha256(b"t2air-2026-11|a|b").hexdigest()[:12], 16)
    assert h("x") < 16**12


def test_a_fare_is_the_same_in_another_process() -> None:
    """Python's `hash()` is salted per process; the fares never use it."""
    code = (
        "from datetime import date;"
        "from flight_voice.airline.fares import economy_fare;"
        "from flight_voice.airline.schedule import departures;"
        "print([economy_fare(d) for d in departures('RUH', 'LHR', date(2026, 12, 17))])"
    )
    shell = child_shell() | {"PYTHONHASHSEED": "12345"}
    done = subprocess.run(
        [sys.executable, "-c", code], env=shell, capture_output=True, check=True, text=True
    )
    here = [economy_fare(d) for d in departures("RUH", "LHR", THURSDAY)]
    assert done.stdout.strip() == str(here) == "[3560, 3780]"


def test_round10_rounds_half_up_to_tens() -> None:
    assert [round10(Fraction(v)) for v in ("3555", "3554.99", "3565", "0", "4", "5")] == [
        3560,
        3550,
        3570,
        0,
        0,
        10,
    ]


def test_the_formula_on_a_known_flight() -> None:
    """T2 401 on Thursday 17 December: 2350 x 1.20 (Thursday) x 1.30 (winter break), no deal,
    jitter 0.97: 3556.0... rounded to 3560; business and first from that."""
    d = _on(401, THURSDAY)
    assert not deal_day("RUH", "LHR", THURSDAY)
    assert h("jitter", "401", "2026-12-17") % 3 == 0
    assert economy_fare(d) == round10(2350 * Fraction("1.2") * Fraction("1.3") * Fraction("0.97"))
    assert (fare(d, "economy"), fare(d, "business"), fare(d, "first")) == (3560, 11390, 19580)
    assert fare(d, "business") == round10(3560 * Fraction("3.2"))
    assert fare(d, "first") == round10(3560 * Fraction("5.5"))


def test_every_fare_is_whole_tens_and_first_only_where_sold() -> None:
    for other in (c for c in CODES if c != HOME):
        for origin, destination in ((HOME, other), (other, HOME)):
            for d in departures(origin, destination, THURSDAY):
                for cabin in CABINS:
                    value = fare(d, cabin)
                    if cabin in d.flight.cabins:
                        assert value is not None and value > 0 and value % 10 == 0
                    else:
                        assert value is None and seats_left(d.flight, THURSDAY, cabin) == 0


def test_the_base_fares_are_the_same_both_ways() -> None:
    """A Sunday out of season, past 06:00, on no deal day and with jitter 1.00 costs the base."""
    sunday = date(2026, 11, 22)
    for other, base in BASE.items():
        for origin, destination in ((HOME, other), (other, HOME)):
            for d in departures(origin, destination, sunday):
                plain = (
                    d.flight.departs.hour >= 6
                    and not deal_day(origin, destination, sunday)
                    and h("jitter", str(d.flight.number), sunday.isoformat()) % 3 == 1
                )
                if plain:
                    assert economy_fare(d) == base


@pytest.mark.parametrize("weekday", range(7))
def test_the_weekday_factor(weekday: int) -> None:
    factors = ("0.90", "0.85", "0.95", "1.20", "1.10", "1.05", "1.00")
    day = date(2026, 11, 16) + timedelta(days=weekday)  # Monday first
    d = _on(103, day)  # Jeddah, 10:30
    expected = 390 * Fraction(factors[day.weekday()])
    if deal_day("RUH", "JED", day):
        expected *= Fraction("0.8")
    expected *= (Fraction("0.97"), Fraction(1), Fraction("1.03"))[
        h("jitter", "103", day.isoformat()) % 3
    ]
    assert economy_fare(d) == round10(expected)


def test_an_early_departure_and_a_deal_day_are_cheaper() -> None:
    deal = first_deal_day("RUH", "IST")
    assert deal == date(2026, 11, 17) and deal_day("RUH", "IST", deal)
    early, late = departures("RUH", "IST", deal)  # 02:10 and 11:50
    assert early.flight.departs.hour < 6 <= late.flight.departs.hour
    no_deal = 1450 * Fraction("0.85")
    jitter = (Fraction("0.97"), Fraction(1), Fraction("1.03"))
    for d, early_factor in ((early, Fraction("0.9")), (late, Fraction(1))):
        j = jitter[h("jitter", str(d.flight.number), deal.isoformat()) % 3]
        assert economy_fare(d) == round10(no_deal * early_factor * Fraction("0.8") * j)


def test_seats_by_cabin() -> None:
    for d in departures("RUH", "LHR", THURSDAY):
        economy = seats_left(d.flight, THURSDAY, "economy")
        assert economy == 0 or 4 <= economy <= 60
        assert 0 <= seats_left(d.flight, THURSDAY, "business") <= 8
        assert 0 <= seats_left(d.flight, THURSDAY, "first") <= 4
    assert seats_left(_on(401, THURSDAY).flight, THURSDAY, "first") == 2
    assert seats_left(_on(201, THURSDAY).flight, THURSDAY, "first") == 0  # an A321neo


def test_the_calendar_gives_each_days_cheapest_and_none_for_no_flight() -> None:
    days = calendar("RUH", "SIN", date(2026, 11, 16), date(2026, 11, 22))
    assert [d.day for d in days] == [date(2026, 11, 16) + timedelta(days=n) for n in range(7)]
    assert [d.fare is None for d in days] == [False, True, False, False, False, False, False]
    for d in days[2:]:
        assert d.fare == min(economy_fare(x) for x in departures("RUH", "SIN", d.day))
    january = calendar("RUH", "IST", date(2027, 1, 1), date(2027, 1, 3))
    assert [d.fare for d in january] == [1920, 1730, 1700]


@pytest.mark.parametrize(
    ("origin", "destination", "pinned"),
    [("RUH", "CAI", (301, date(2026, 11, 18))), ("RUH", "CDG", (451, date(2026, 11, 18)))],
)
def test_the_pinned_business_sell_outs_still_hold(
    origin: Code, destination: Code, pinned: tuple[int, date]
) -> None:
    assert business_sold_out(origin, destination) == pinned
    number, day = pinned
    flight = _on(number, day).flight
    assert seats_left(flight, day, "business") == 0 < seats_left(flight, day, "economy")


def test_the_pinned_no_flight_day_still_holds() -> None:
    assert no_flight_day("RUH", "SIN") == date(2026, 11, 17)
    assert no_flight_day("RUH", "SIN", date(2026, 11, 18)) == date(2026, 11, 24)
    assert no_flight_day("RUH", "LHR") is None
    assert TODAY.weekday() == 0
