"""`search_flights` over a span of days (tools/overview.py), run as the talker's call would run
it: "next week" answered at once, before any return day is asked for, with the span's days, the
route's daily times, each day's lowest fare and the two cheapest marked, writing nothing to the
draft (the owner's live call made a Monday up and asked for the day twice); a Singapore span says
its Tuesday has no flight; a span past the window, a cabin the route does not sell and a search
that does not answer each have their own answer; and the calendar of flights, one row a day,
passes the output guard's ID rule in every language."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from flight_voice.airline.fares import calendar
from flight_voice.said import Tag
from flight_voice.tools.results import SAY, SEARCH_FAILED
from flight_voice.tools.search import search_flights
from flight_voice.trip import TripBook

from tests.flight_voice.tools.tool_support import TAGS, airline, card_passes, data, run

NEXT_WEEK: dict[str, Any] = {"kind": "days", "span": "next_week"}


def _span(tag: Tag = "en", trips: TripBook | None = None, **arguments: Any) -> Any:
    tool = search_flights(airline(), trips if trips is not None else TripBook())
    return run(tool, tag, **arguments)


@pytest.mark.parametrize("tag", TAGS)
def test_next_week_is_answered_at_once_with_its_days_times_and_two_cheapest(tag: Tag) -> None:
    trips = TripBook()
    made = _span(tag, trips, destination="London" if tag == "en" else "لندن", depart=NEXT_WEEK)
    found = data(made)
    assert (found["status"], found["say"]) == ("days", SAY["days"])
    assert (found["first"]["iso"], found["last"]["iso"]) == ("2026-11-22", "2026-11-28")
    assert found["departs"] == ["09:10", "14:40"] and "no_flight_days" not in found
    days = found["days"]
    assert [d["date"]["iso"] for d in days] == [f"2026-11-{n}" for n in range(22, 29)]
    lowest = calendar("RUH", "LHR", date(2026, 11, 22), date(2026, 11, 28))
    assert [d["fare_sar"] for d in days] == [d.fare for d in lowest]
    cheapest = sorted(days, key=lambda d: (d["fare_sar"], d["date"]["iso"]))[:2]
    assert [d for d in days if d.get("mark") == "cheapest"] == sorted(
        cheapest, key=lambda d: d["date"]["iso"]
    )
    assert len(trips) == 0  # no day the caller did not choose is kept
    assert made.card is not None and len(made.card.rows) == 7 and card_passes(made)
    assert [row.mark for row in made.card.rows].count("best") == 2
    assert made.card.slot == "outbound"  # the calendar of flights, in the outbound segment
    if tag == "en":
        assert made.card.title == "Outbound: Riyadh to London · Sun 22 Nov to Sat 28 Nov · economy"


def test_a_span_comes_before_the_round_trip_gate_and_a_return_day() -> None:
    """With no return day said, a round trip's span still answers what flies."""
    found = data(_span(destination="Paris", depart={"kind": "days", "span": "this_weekend"}))
    assert found["status"] == "days"
    assert (found["first"]["iso"], found["last"]["iso"]) == ("2026-11-20", "2026-11-21")
    assert len(found["days"]) == 2


def test_a_span_with_a_day_of_no_flight_names_it_and_its_card_marks_it() -> None:
    made = _span(destination="Singapore", depart=NEXT_WEEK)
    found = data(made)
    assert found["say"] == SAY["days_some"]
    assert [d["iso"] for d in found["no_flight_days"]] == ["2026-11-24"]
    assert len(found["days"]) == 6 and found["departs"] == ["22:05"]
    assert made.card is not None and card_passes(made)
    marks = [row.mark for row in made.card.rows]
    assert len(marks) == 7 and marks[2] == "unavailable" and marks.count("best") == 2
    assert made.card.rows[2].detail == "No flight"


@pytest.mark.parametrize("tag", TAGS)
def test_the_calendar_of_flights_passes_the_id_rule_in_each_language(tag: Tag) -> None:
    for span in ("this_week", "next_week", "this_weekend", "next_weekend", "coming"):
        made = _span(tag, destination="Dubai", depart={"kind": "days", "span": span})
        assert made.ok and made.card is not None and card_passes(made), (tag, span)
        assert made.evidence == made.card.texts()


def test_a_cabin_the_route_does_not_sell_and_a_failed_search_have_their_answers() -> None:
    first = data(_span(destination="Dubai", depart=NEXT_WEEK, cabin="first"))
    assert first["status"] == "cabin_not_offered"
    failed = run(
        search_flights(airline(search_mode="fail"), TripBook()),
        destination="London",
        depart=NEXT_WEEK,
    )
    assert not failed.ok and failed.data == {"error": SEARCH_FAILED}


def test_a_span_that_is_not_one_of_the_five_is_refused() -> None:
    refused = _span(destination="London", depart={"kind": "days", "span": "someday"})
    assert not refused.ok and "depart" in str(refused.data)
    back = _span(
        destination="London", depart={"kind": "on", "day": 17, "month": 12}, return_date=NEXT_WEEK
    )
    assert not back.ok  # a span is a departure's only
