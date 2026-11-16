"""A caller's pick read against the options listed, in the order said: by number, the cheapest
(of those with a seat for every traveler), the earliest, the latest, a part of the day and a
departure time; a pick that names none or several gives them all back, and a pick the talker
passes in a shape the schema does not hold is refused."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from flight_voice.airline.fares import fare
from flight_voice.airline.schedule import departures
from flight_voice.tools.picks import Choice, departure_of, pick
from flight_voice.trip import Shown
from pydantic import TypeAdapter, ValidationError

from tests.flight_voice.scenario_dates import TODAY, business_sold_out

DEC_17 = date(2026, 12, 17)
CHOICE: TypeAdapter[Choice] = TypeAdapter(Choice)


def _shown(origin: str, destination: str, day: date) -> tuple[Shown, ...]:
    flown = departures(origin, destination, day)  # type: ignore[arg-type]
    return tuple(Shown(n=n, flight=d.flight.number, day=day) for n, d in enumerate(flown, 1))


LONDON = _shown("RUH", "LHR", DEC_17)  # 09:10 (401), 14:40 (403)
JEDDAH = _shown("RUH", "JED", DEC_17)  # 06:00, 10:30, 15:00, 21:00


def _picked(choice: dict[str, Any], shown: tuple[Shown, ...], **kept: Any) -> list[int]:
    cabin = kept.get("cabin", "economy")
    named = pick(CHOICE.validate_python(choice), shown, cabin, kept.get("travelers", 1))
    return [s.flight for s in named]


@pytest.mark.parametrize(
    ("choice", "flights"),
    [
        ({"pick": "number", "n": 2}, [403]),
        ({"pick": "number", "n": 3}, []),
        ({"pick": "earliest"}, [401]),
        ({"pick": "latest"}, [403]),
        ({"pick": "part_of_day", "part": "morning"}, [401]),
        ({"pick": "part_of_day", "part": "afternoon"}, [403]),
        ({"pick": "part_of_day", "part": "evening"}, []),
        ({"pick": "time", "departs": "9:10"}, [401]),
        ({"pick": "time", "departs": "14:40"}, [403]),
        ({"pick": "time", "departs": "10:00"}, []),
    ],
)
def test_each_pick_names_the_options_it_means(choice: dict[str, Any], flights: list[int]) -> None:
    assert _picked(choice, LONDON) == flights


def test_a_part_of_the_day_two_flights_share_names_both_in_the_order_listed() -> None:
    assert _picked({"pick": "part_of_day", "part": "morning"}, JEDDAH) == [101, 103]
    assert _picked({"pick": "part_of_day", "part": "evening"}, JEDDAH) == [107]


def test_the_cheapest_is_the_lowest_fare_and_the_first_listed_of_two_as_cheap() -> None:
    fares = {s.flight: fare(departure_of(s), "economy") or 0 for s in JEDDAH}
    cheapest = min(fares.values())
    first = next(n for n, f in fares.items() if f == cheapest)
    assert _picked({"pick": "cheapest"}, JEDDAH) == [first]


def test_the_cheapest_skips_a_flight_without_a_seat_for_every_traveler() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    shown = _shown("RUH", "CAI", day)
    picked = _picked({"pick": "cheapest"}, shown, cabin="business")
    assert picked != [number] and len(picked) == 1


def test_the_cheapest_of_options_all_full_is_still_the_lowest_fare() -> None:
    shown = _shown("RUH", "CAI", TODAY)
    assert len(_picked({"pick": "cheapest"}, shown, travelers=9, cabin="business")) == 1


@pytest.mark.parametrize(
    "choice",
    [
        {"pick": "number", "n": 5},
        {"pick": "number", "n": 0},
        {"pick": "time", "departs": "25:00"},
        {"pick": "time", "departs": "nine"},
        {"pick": "part_of_day", "part": "dawn"},
        {"pick": "second"},
        {"pick": "cheapest", "flight": 401},
    ],
)
def test_a_pick_in_a_shape_the_schema_does_not_hold_is_refused(choice: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CHOICE.validate_python(choice)
