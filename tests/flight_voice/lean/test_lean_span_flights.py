"""A span's flights day by day (`find_flights(flights_per_day=true)`, flight_voice/lean/span.py
and span_days.py, plan 011's round 2: asked for the priciest flight of a span, the model had
only each day's lowest price): every day is searched, and each gives its flights, its lowest
and highest prices, its first and last departures and its airlines, over the flights its own
search lists from, with a note that a day's flights come at once from find_flights for that
day; the priciest is then listed to choose. Without the flag a span stays the one-search
calendar. The flag is the real network's: the mock's search has none (nor `one_way`), as run F
reads it; its timetable still gives the same day by day to the real network's search. A span
longer than two weeks is cut, the days after offered."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Final

from flight_voice.flight_data.model import Money, Offer
from flight_voice.flight_data.queries import DayFare, DayFares, SpanQuery
from flight_voice.lean.find import find_flights
from flight_voice.lean.find_schema import REAL_ONLY, RETURN
from flight_voice.lean.span import CHECKED_LAST, TO_PICK
from flight_voice.lean.weekday import SAID

from tests.flight_voice.flight_data.fake import (
    FLYADEAL,
    FLYNAS,
    JEDDAH,
    RIYADH,
    SAUDIA,
    FakeFlightData,
    answered,
    nonstop,
    query,
)
from tests.flight_voice.lean.lean_support import LeanCall, lean_deps
from tests.flight_voice.lean.real_support import real_call
from tests.flight_voice.tools.tool_support import card_passes, data

FIRST: Final = date(2026, 11, 22)
DAYS: Final = 3


def _at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0)


def _day(day: date, n: int) -> tuple[Offer, ...]:
    route = ("RUH", "JED")
    return (
        nonstop(FLYNAS, "17", route, _at(day, 6), 105, 400 + n),
        nonstop(SAUDIA, "1020", route, _at(day, 9), 110, 1900 + 100 * n),  # the priciest
        nonstop(FLYADEAL, "111", route, _at(day, 21), 110, 450 + n),
    )


def _source() -> FakeFlightData:
    data_ = FakeFlightData()
    for n in range(DAYS):
        day = FIRST + timedelta(days=n)
        data_.set(answered(query(RIYADH, JEDDAH, day), _day(day, n)))
    span = SpanQuery(origin=RIYADH, destination=JEDDAH, first=FIRST, last=FIRST)
    priced = DayFare(day=FIRST, lowest=Money(amount=400), flights=None)
    data_.spans["RUH-JED"] = DayFares(query=span, status="ok", days=(priced,))
    return data_


def _span(**more: Any) -> dict[str, Any]:
    last = FIRST + timedelta(days=DAYS - 1)
    return {"first": FIRST.isoformat(), "last": last.isoformat(), **more}


def test_each_day_is_searched_and_summed_up_beyond_its_cheapest() -> None:
    source = _source()
    call = real_call(source)
    found = call.find(destination="Jeddah", depart=_span(), flights_per_day=True)
    answer = data(found)
    assert source.calls["day"] == DAYS  # each day searched, no fare calendar
    first = answer["days"][0]
    assert first == {
        "date": FIRST.isoformat(),
        "weekday": "Sunday",
        "flights": 3,
        "lowest_price": 400,
        "highest_price": 1900,
        "first_departs": "06:00",
        "last_departs": "21:00",
        "airlines": ["flynas", "Saudia", "flyadeal"],
    }
    assert [d["highest_price"] for d in answer["days"]] == [1900, 2000, 2100]
    assert answer["note"] == TO_PICK
    assert found.card is not None and card_passes(found)
    assert call.draft.destination is None  # a span writes nothing to the trip


def test_the_priciest_day_and_flight_are_then_chosen_at_once() -> None:
    source = _source()
    call = real_call(source)
    answer = data(call.find(destination="Jeddah", depart=_span(), flights_per_day=True))
    dearest = max(answer["days"], key=lambda d: d["highest_price"])
    day = data(call.find(destination="Jeddah", depart=dearest["date"]))
    priciest = max(day["outbound"]["options"], key=lambda o: o["price"])
    assert priciest["price"] == dearest["highest_price"] == 2100
    picked = data(call.choose(outbound_id=priciest["id"]))
    assert picked["total"] == 2100 and picked["outbound"]["airline"] == "Saudia"


def test_without_the_flag_a_span_stays_the_one_search_calendar() -> None:
    source = _source()
    answer = data(real_call(source).find(destination="Jeddah", depart=_span()))
    assert source.calls == {"day": 0, "days": 1, "nearest": 0}
    assert "highest_price" not in answer["days"][0] and answer["note"] != TO_PICK


def _over_the_mock() -> LeanCall:
    """The real network's search over the mock's timetable (its exact days)."""
    return LeanCall(deps=replace(lean_deps(), bookable=False, network="real"))


def test_the_mocks_search_has_no_flag_as_run_f_reads_it() -> None:
    mock_schema = dict(find_flights(lean_deps()).tool_schema().parameters)
    real_schema = dict(find_flights(_over_the_mock().deps).tool_schema().parameters)
    mock, real = mock_schema.pop("properties"), real_schema.pop("properties")
    assert isinstance(mock, dict) and isinstance(real, dict)
    assert REAL_ONLY == ("flights_per_day", "one_way")
    assert not set(REAL_ONLY) & set(mock) and set(REAL_ONLY) <= set(real)
    # The same fields, the weekdays' and the return day's described as run F read them (the
    # real network asks for a weekday plainly: weekday.py's SAID_OUT, SAID_BACK).
    told = {"depart_weekday": SAID, "return_weekday": SAID, "return_date": RETURN}
    as_before: dict[str, object] = {}
    for name, held in real.items():
        if name not in REAL_ONLY:
            assert isinstance(held, dict)
            as_before[name] = {**held, **({"description": told[name]} if name in told else {})}
    assert mock == as_before
    assert mock_schema == real_schema  # the same required fields and definitions
    refused = LeanCall().find(destination="Jeddah", depart=_span(), flights_per_day=True)
    assert not refused.ok and refused.failure == "bad_arguments"


def test_the_mock_gives_each_days_flights_from_its_timetable() -> None:
    call = _over_the_mock()
    span = {"first": "2026-11-16", "last": "2026-11-22"}
    answer = data(call.find(destination="Singapore", depart=span, flights_per_day=True))
    for day in answer["days"]:
        listed = data(call.find(destination="Singapore", depart=day["date"]))["outbound"]
        prices = [o["price"] for o in listed["options"]]
        assert (day["flights"], day["lowest_price"], day["highest_price"]) == (
            listed["count"],
            min(prices),
            max(prices),
        )
        assert day["airlines"] == ["T2 Air"]
    assert [d["date"] for d in answer["no_flight_days"]] == ["2026-11-17"]


def test_a_span_longer_than_two_weeks_is_cut_and_the_days_after_offered() -> None:
    answer = data(
        _over_the_mock().find(
            destination="Singapore",
            depart={"first": "2026-11-16", "last": "2026-12-15"},
            flights_per_day=True,
        )
    )
    assert answer["checked_last"] == "2026-11-29" and CHECKED_LAST in answer["note"]
    assert answer["last"]["date"] == "2026-11-29" and not answer.get("weeks")
    assert all("highest_price" in d for d in answer["days"])
