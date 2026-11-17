"""A caller's pick read against the options listed, in the order said: by number (the only one
listed too), the cheapest and the dearest (of those with a seat for every traveler, the first
listed of two at one fare), the earliest, the latest, a part of the day, a departure time and a
fare; a pick that names none or several gives them all back, and a pick the talker passes in a
shape the schema does not hold is refused; and each kind's description says when it is the
caller's, its part-of-day hours the code's."""

from __future__ import annotations

import re
from datetime import date, time
from typing import Any

import pytest
from flight_voice.airline.fares import fare
from flight_voice.airline.schedule import departures
from flight_voice.said.words import part_of_day
from flight_voice.tools.picks import (
    ByFare,
    ByNumber,
    ByPart,
    ByTime,
    Choice,
    Dearest,
    Earliest,
    Latest,
    departure_of,
    pick,
)
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
# Jeddah back on Thursday 19 November: 07:45 (102) and 17:15 (106) at 470, 12:30 and 23:00 at
# 450; on Friday the 20th, 17:15 alone at 430.
BACK_19 = _shown("JED", "RUH", date(2026, 11, 19))
BACK_20 = _shown("JED", "RUH", date(2026, 11, 20))


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


def test_the_only_flight_listed_is_its_number_one() -> None:
    singapore = _shown("RUH", "SIN", DEC_17)
    assert len(singapore) == 1
    assert _picked({"pick": "number", "n": 1}, singapore) == [singapore[0].flight]


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


def _fares(shown: tuple[Shown, ...]) -> list[int]:
    return [fare(departure_of(s), "economy") or 0 for s in shown]


def test_the_dearest_is_the_highest_fare_and_the_first_listed_of_two_as_dear() -> None:
    assert _fares(BACK_19) == [470, 450, 470, 450]
    assert _picked({"pick": "dearest"}, BACK_19) == [102]
    assert _picked({"pick": "dearest"}, LONDON) == [403]


def test_the_dearest_skips_a_flight_without_a_seat_and_names_one_when_all_are_full() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    shown = _shown("RUH", "CAI", day)
    picked = _picked({"pick": "dearest"}, shown, cabin="business")
    assert picked != [number] and len(picked) == 1
    full = _shown("RUH", "CAI", TODAY)
    assert len(_picked({"pick": "dearest"}, full, travelers=9, cabin="business")) == 1


def test_a_fare_said_names_each_option_at_that_fare_in_the_cabin() -> None:
    assert _picked({"pick": "fare", "fare_sar": 430}, BACK_20) == [106]
    assert _picked({"pick": "fare", "fare_sar": 470}, BACK_19) == [102, 106]
    assert _picked({"pick": "fare", "fare_sar": 999}, BACK_19) == []
    business = fare(departure_of(LONDON[0]), "business")
    assert business is not None
    assert _picked({"pick": "fare", "fare_sar": business}, LONDON, cabin="business") == [401]
    assert _picked({"pick": "fare", "fare_sar": business}, LONDON) == []


@pytest.mark.parametrize(
    "choice",
    [
        {"pick": "fare", "fare_sar": 0},
        {"pick": "fare", "fare_sar": "four hundred"},
        {"pick": "fare"},
        {"pick": "dearest", "n": 1},
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


def test_each_kind_says_when_it_is_the_callers_and_the_parts_hours_are_the_codes() -> None:
    """f-dev-5: a part of the day or a later one passed as a time or a number, and a time the
    caller never said. Each kind's description (the schema's) says when it is used, and the
    hours it gives a part of the day are the ones `pick` reads."""
    kinds = (ByNumber, Dearest, Earliest, Latest, ByPart, ByTime, ByFare)
    texts = {kind.__name__: " ".join((kind.__doc__ or "").split()) for kind in kinds}
    # The owner's live calls: "the most expensive" had no kind, and a fare said went as a time.
    assert "whenever the caller picks by the highest fare" in texts["Dearest"]
    assert "a fare the caller said themselves" in texts["ByFare"]
    assert "never its number" in texts["Dearest"] and "nor its number" in texts["ByFare"]
    assert "only when the caller said a number or an order word" in texts["ByNumber"]
    # f10: "this one" after a one-flight listing has a kind; a said time is never earliest or
    # latest (f18's "The 10:30 one."), and the Arabic latest names leaving, as "out" does.
    assert "or picked the only flight listed" in texts["ByNumber"]
    assert "A comparison of when it leaves is earliest or latest" in texts["ByNumber"]
    assert all("never its number" in texts[k] for k in ("Earliest", "Latest"))
    assert "«آخر وحدة تطلع»" in texts["Latest"]
    assert "a part of the day the caller named, even when you know its time" in texts["ByPart"]
    assert "a time the caller said themselves" in texts["ByTime"]
    hours = re.findall(r"(\w+) (?:is )?(\d\d:\d\d) to (\d\d:\d\d)", texts["ByPart"])
    assert [part.lower() for part, _, _ in hours] == ["morning", "afternoon", "evening", "night"]
    for part, start, end in hours:
        for at in (start, end):
            assert part_of_day(time.fromisoformat(at)) == part.lower(), (part, at)
