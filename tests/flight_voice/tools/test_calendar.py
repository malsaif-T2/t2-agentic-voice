"""`fare_calendar`, run as the talker's call would run it: the span a month, a date form or
neither names, kept to the booking window, the year chosen in code; the seven cheapest days in
date order, every one in the data, the three cheapest marked, the span's highest fare; the cabin
asked for, or else the trip's; a day with no flight left out and counted, never given a fare;
each refusal with its status; a calendar that does not answer said as a failure; and its card
passing the output guard's ID rule."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest
from flight_voice.airline import fares
from flight_voice.airline.airports import Code
from flight_voice.airline.system import Airline
from flight_voice.said import Tag
from flight_voice.tools.calendar import BOTH, FARE_CALENDAR, fare_calendar
from flight_voice.tools.results import SAY, SEARCH_FAILED
from flight_voice.trip import TripBook

from tests.flight_voice.scenario_dates import TODAY
from tests.flight_voice.tools.tool_support import (
    DEC_17,
    TAGS,
    Call,
    airline,
    card_passes,
    data,
    run,
)


def _calendar(tag: Tag = "en", flights: Airline | None = None, **arguments: Any) -> Any:
    tool = fare_calendar(flights if flights is not None else airline(), TripBook())
    return run(tool, tag, **arguments)


def _found(tag: Tag = "en", **arguments: Any) -> dict[str, Any]:
    made = _calendar(tag, **arguments)
    assert made.ok, made.data
    return data(made)


def test_a_month_gives_its_seven_cheapest_days_in_date_order_the_three_cheapest_marked() -> None:
    found = _found(destination="Istanbul", month=1)
    assert (found["status"], found["say"], found["month_said"]) == (
        "ok",
        SAY["calendar"],
        "January",
    )
    assert (found["first"]["iso"], found["last"]["iso"]) == ("2027-01-01", "2027-01-31")
    span = fares.calendar("RUH", "IST", date(2027, 1, 1), date(2027, 1, 31))
    by_day = {d.day.isoformat(): d.fare for d in span}
    days = found["days"]
    isos = [d["iso"] for d in (x["date"] for x in days)]
    assert len(days) == 7 and isos == sorted(isos)
    assert all(by_day[d["date"]["iso"]] == d["fare_sar"] for d in days)
    shown = {d["fare_sar"] for d in days}
    assert max(shown) <= min(f for f in by_day.values() if f is not None and f not in shown)
    marked = [d["fare_sar"] for d in days if d.get("mark") == "cheapest"]
    unmarked = [d["fare_sar"] for d in days if "mark" not in d]
    assert len(marked) == 3 and max(marked) <= min(unmarked)
    assert found["highest_sar"] == max(f for f in by_day.values() if f is not None)
    assert found["route_said"] == "Riyadh to Istanbul" and "no_flight_days" not in found
    assert found["fare_basis_said"] == "per person, one way"


@pytest.mark.parametrize(
    ("arguments", "first", "last"),
    [
        ({"month": 11}, "2026-11-16", "2026-11-30"),
        ({"month": 3}, "2027-03-01", "2027-03-16"),
        ({"from_date": {"kind": "relative", "when": "tomorrow"}}, "2026-11-17", "2026-12-16"),
        ({}, "2026-11-16", "2026-12-15"),
    ],
)
def test_the_span_is_the_month_from_today_or_thirty_days_inside_the_window(
    arguments: dict[str, Any], first: str, last: str
) -> None:
    found = _found(destination="Dubai", **arguments)
    assert (found["first"]["iso"], found["last"]["iso"]) == (first, last)


@pytest.mark.parametrize(
    ("arguments", "status", "say"),
    [
        ({"month": 5}, "date_problem", "beyond_window"),
        ({"from_date": {"kind": "on", "day": 31, "month": 11}}, "date_problem", "no_such_day"),
        ({"from_date": {"kind": "nights", "nights": 2}}, "date_problem", "return_only"),
        ({"destination": "Manchester"}, "not_served", "not_served_city"),
        ({"origin": "Jeddah"}, "not_served", "not_served_route"),
        ({"cabin": "first"}, "cabin_not_offered", "cabin_not_offered"),
    ],
)
def test_each_refusal_gives_its_status_and_its_fixed_say(
    arguments: dict[str, Any], status: str, say: str
) -> None:
    found = _found(**({"destination": "Dubai"} | arguments))
    assert (found["status"], found["say"]) == (status, SAY[say])


def test_singapore_tuesdays_are_left_out_and_counted_never_given_a_fare() -> None:
    found = _found(destination="Singapore", month=12)
    assert found["no_flight_days"] == 5  # the Tuesdays of December 2026
    assert all(d["date"]["weekday"] != "Tuesday" for d in found["days"])


def test_a_cabin_gives_that_cabins_fares() -> None:
    economy = _found(destination="London", month=1)
    business = _found(destination="London", month=1, cabin="business")
    assert business["cabin_said"] == "business class" and economy["cabin"] == "economy"
    assert min(d["fare_sar"] for d in business["days"]) > min(
        d["fare_sar"] for d in economy["days"]
    )


def test_a_cabin_left_out_is_the_trips() -> None:
    """f27: «أنا وزوجتي نبي نسافر على البزنس», then a search in business, then the cheapest
    days: left out, the cabin is the call's draft's, never economy by default."""
    call = Call("ar-SA")
    tool = fare_calendar(call.airline, call.trips)
    assert data(run(tool, "ar-SA", destination="دبي", month=12))["cabin"] == "economy"
    call.search(destination="دبي", depart=DEC_17, one_way=True, cabin="business")
    found = data(run(tool, "ar-SA", destination="دبي", month=12))
    assert (found["status"], found["cabin"]) == ("ok", "business")
    asked = data(run(tool, "ar-SA", destination="دبي", month=12, cabin="business"))
    assert found["days"] == asked["days"]
    economy = data(run(tool, destination="Dubai", cabin="economy"))
    assert economy["cabin"] == "economy" and call.draft.cabin == "business"


def test_a_month_and_a_date_together_are_told_back_as_a_failure() -> None:
    both = _calendar(destination="Dubai", month=1, from_date={"kind": "relative", "when": "today"})
    assert not both.ok and both.data == {"error": BOTH}


@pytest.mark.parametrize("tag", TAGS)
def test_a_calendar_that_does_not_answer_is_said_as_a_failure(tag: Tag) -> None:
    failed = _calendar(tag, airline(search_mode="fail"), destination="Dubai", month=1)
    assert not failed.ok and failed.data == {"error": SEARCH_FAILED} and failed.card is None


class _NoFlights(Airline):
    async def calendar(
        self, origin: Code, destination: Code, first: date, last: date, cabin: Any = "economy"
    ) -> tuple[fares.FareDay, ...]:
        days = (last - first).days + 1
        return tuple(fares.FareDay(first + timedelta(days=n), None) for n in range(days))


def test_a_span_with_no_flight_at_all_offers_the_nearest_days() -> None:
    found = data(_calendar("en", _NoFlights(today=lambda: TODAY), destination="Dubai"))
    assert (found["status"], found["say"]) == ("no_flights_that_day", SAY["no_flights_that_day"])
    assert len(found["nearest"]) == 2


@pytest.mark.parametrize("tag", TAGS)
def test_the_card_shows_the_seven_days_and_passes_the_id_rule(tag: Tag) -> None:
    for arguments in ({"month": 1}, {"from_date": {"kind": "on", "day": 17, "month": 12}}):
        made = _calendar(tag, destination="Istanbul", **arguments)
        assert made.card is not None and len(made.card.rows) == 7 and card_passes(made)
        assert made.card.steps == () and all(row.value for row in made.card.rows)
    english = _calendar("en", destination="Istanbul", month=1).card
    assert english is not None and english.title == "Riyadh to Istanbul, cheapest days in January"
    assert [row.mark for row in english.rows].count("best") == 3
    assert {row.mark for row in english.rows} == {"best", None}
    cheapest = sorted(english.rows, key=lambda row: int(row.value.split()[0].replace(",", "")))
    assert {row.mark for row in cheapest[:3]} == {"best"}
    assert english.rows[0].title.split()[0] in {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    arabic = _calendar("ar-SA", destination="إسطنبول", month=1).card
    assert arabic is not None and arabic.title == "الرياض إلى إسطنبول، أرخص الأيام في يناير"


def test_the_talker_sees_its_arguments_and_the_calendars_progress_line() -> None:
    tool = fare_calendar(airline(), TripBook())
    schema = tool.tool_schema()
    assert schema.name == FARE_CALENDAR and tool.progress == "fares"
    assert dict(schema.parameters)["required"] == ["destination"]
    cabin = json.loads(json.dumps(dict(schema.parameters)))["properties"]["cabin"]
    assert cabin["default"] is None and "economy" not in cabin["description"]
    assert cabin["description"] == (
        "The cabin the caller asked for at any point in this call; else leave it out."
    )
    assert len(str(data(_calendar(destination="Istanbul", month=1)))) < 1700
    assert TODAY.isoformat() == "2026-11-16"
