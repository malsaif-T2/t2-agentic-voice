"""`search_flights`, run as the talker's call would run it: every status in its order of checks,
each with its fixed `say`; a listing of at most four options with the cheapest marked, the fare's
basis and the words in the reply's registers; the draft written only by a search that lists or
asks for the return; a search that fails said as a failure; a date that is not a date form
refused with its field named; and the schema the talker sees."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import find_flight
from flight_voice.said import Tag
from flight_voice.tools.results import SAY, SEARCH_FAILED
from flight_voice.tools.search import SEARCH_FLIGHTS, search_flights
from flight_voice.trip import Shown, TripBook

from tests.flight_voice.scenario_dates import business_sold_out
from tests.flight_voice.tools.tool_support import CALL_ID, TAGS, airline, data, run

DEC_17: dict[str, Any] = {"kind": "on", "day": 17, "month": 12}
DEC_20: dict[str, Any] = {"kind": "on", "day": 20, "month": 12}
TOMORROW: dict[str, Any] = {"kind": "relative", "when": "tomorrow"}


def _search(tag: Tag = "en", trips: TripBook | None = None, **arguments: Any) -> dict[str, Any]:
    tool = search_flights(airline(), trips if trips is not None else TripBook())
    result = run(tool, tag, **arguments)
    assert result.ok, result.data
    return data(result)


def test_london_lists_its_two_flights_the_cheapest_marked_and_the_draft_holds_them() -> None:
    trips = TripBook()
    found = _search("en", trips, destination="London", depart=DEC_17, return_date=DEC_20)
    assert (found["status"], found["leg"], found["route_said"]) == (
        "ok",
        "outbound",
        "Riyadh to London",
    )
    assert found["date"] == {
        "iso": "2026-12-17",
        "day": 17,
        "month": "December",
        "weekday": "Thursday",
    }
    assert found["return_date"]["iso"] == "2026-12-20"
    first, second = found["options"]
    assert (first["flight"], first["departs"], first["arrives"], first["fare_sar"]) == (
        "T2 401",
        "09:10",
        "13:15",
        3560,
    )
    assert first["duration"] == {"hours": 7, "minutes": 5} and first["mark"] == "cheapest"
    assert second["departs"] == "14:40" and "mark" not in second
    assert found["fare_basis_said"] == "per person, one way" and found["say"] == SAY["listed"]
    assert (found["travelers"], found["cabin"], found["cabin_said"]) == (1, "economy", "economy")
    draft = trips.get(CALL_ID)
    assert (draft.destination, draft.depart, draft.return_date) == (
        "LHR",
        date(2026, 12, 17),
        date(2026, 12, 20),
    )
    assert draft.shown_outbound == (
        Shown(n=1, flight=401, day=date(2026, 12, 17)),
        Shown(n=2, flight=403, day=date(2026, 12, 17)),
    )


def test_a_saudi_reply_is_given_saudi_words_and_the_msa_beside_them() -> None:
    found = _search("ar-SA", destination="لندن", depart=DEC_17, return_date=DEC_20)
    assert (found["route_said"], found["route_said_msa"]) == (
        "من الرياض للندن",
        "من الرياض إلى لندن",
    )
    assert (found["fare_basis_said"], found["fare_basis_said_msa"]) == (
        "للشخص، رايح بس",
        "للشخص، ذهاب فقط",
    )
    assert found["date"]["weekday"] == "الخميس" and found["date"]["month"] == "ديسمبر"
    assert found["options"][0]["part_of_day_said"] == "الصبح"
    assert found["options"][0]["part_of_day_said_msa"] == "صباحًا"
    assert "cabin_said_msa" not in found  # the same in both registers
    msa = _search("ar", destination="لندن", depart=DEC_17, return_date=DEC_20)
    assert msa["route_said"] == "من الرياض إلى لندن" and "route_said_msa" not in msa


@pytest.mark.parametrize("tag", TAGS)
def test_four_flights_are_listed_and_the_say_asks_for_three_and_how_many_more(tag: Tag) -> None:
    found = _search(tag, destination="Jeddah", depart=TOMORROW, one_way=True, travelers=2)
    assert [o["n"] for o in found["options"]] == [1, 2, 3, 4] and found["more"] == 1
    assert found["say"] == SAY["listed_more"] and found["travelers"] == 2
    marked = [o for o in found["options"] if o.get("mark") == "cheapest"]
    assert len(marked) == 1
    assert marked[0]["fare_sar"] == min(o["fare_sar"] for o in found["options"])
    assert len(json.dumps(found, ensure_ascii=False)) < 1700


def test_a_full_flight_is_listed_as_full_and_never_marked_cheapest() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    flight = find_flight(number)
    assert flight is not None and seats_left(flight, day, "business") == 0
    on: dict[str, Any] = {"kind": "on", "day": day.day, "month": day.month}
    found = _search(destination="Cairo", depart=on, one_way=True, cabin="business")
    by_flight = {o["flight"]: o for o in found["options"]}
    full = by_flight[f"T2 {number}"]
    assert full["seats_ok"] is False and "mark" not in full
    assert found["say"] == SAY["listed_full"]


def test_nine_travelers_in_business_find_no_seats_and_are_offered_economy() -> None:
    found = _search(destination="Dubai", depart=DEC_17, one_way=True, travelers=9, cabin="business")
    assert (found["status"], found["cabin"], found["travelers"]) == ("no_seats", "business", 9)
    assert found["cabins_with_seats"] == ["economy"] and found["say"] == SAY["no_seats"]


@pytest.mark.parametrize(
    ("arguments", "status", "say"),
    [
        ({"destination": "Manchester"}, "not_served", "not_served_city"),
        ({"destination": "أبها"}, "not_served", "not_served_city"),
        ({"destination": "Dubai", "origin": "Jeddah"}, "not_served", "not_served_route"),
        ({"destination": "Riyadh"}, "not_served", "not_served_route"),
        ({"destination": "Dubai", "origin": "Gotham"}, "not_served", "not_served_city"),
        ({"depart": {"kind": "on", "day": 31, "month": 11}}, "date_problem", "no_such_day"),
        ({"depart": {"kind": "on", "day": 1, "month": 4}}, "date_problem", "beyond_window"),
        ({"depart": {"kind": "nights", "nights": 3}}, "date_problem", "return_only"),
        (
            {"return_date": {"kind": "on", "day": 10, "month": 12}},
            "date_problem",
            "return_before_departure",
        ),
        ({"return_date": None}, "needs_return_date", "needs_return_date"),
        ({"destination": "Dubai", "cabin": "first"}, "cabin_not_offered", "cabin_not_offered"),
    ],
)
def test_each_check_gives_its_status_and_its_fixed_say(
    arguments: dict[str, Any], status: str, say: str
) -> None:
    asked: dict[str, Any] = {"destination": "London", "depart": DEC_17, "return_date": DEC_20}
    asked |= arguments
    if asked["return_date"] is None:
        del asked["return_date"]
    found = _search(**asked)
    assert (found["status"], found["say"]) == (status, SAY[say])
    if status == "not_served":
        assert found["served_said"].startswith("Riyadh, Jeddah, Dubai")
    if status == "date_problem":
        assert found["last_day"]["iso"] == "2027-03-16"
    if status == "cabin_not_offered":
        assert found["offered"] == ["economy", "business"]


def test_only_a_search_that_lists_or_asks_for_the_return_writes_the_draft() -> None:
    trips = TripBook()
    _search("en", trips, destination="Manchester", depart=DEC_17, return_date=DEC_20)
    _search("en", trips, destination="London", depart={"kind": "on", "day": 31, "month": 11})
    assert len(trips) == 0
    asked = _search("en", trips, destination="London", depart=DEC_17)
    assert asked["status"] == "needs_return_date"
    draft = trips.get(CALL_ID)
    assert (draft.destination, draft.depart, draft.shown_outbound) == (
        "LHR",
        date(2026, 12, 17),
        (),
    )
    assert draft.missing() == ("return_date", "outbound", "return")


def test_a_singapore_tuesday_has_no_flight_and_offers_the_nearest_days() -> None:
    found = _search(destination="Singapore", depart=TOMORROW, one_way=True)  # Tuesday 11-17
    assert (found["status"], found["leg"], found["say"]) == (
        "no_flights_that_day",
        "outbound",
        SAY["no_flights_that_day"],
    )
    assert [d["iso"] for d in found["nearest"]] == ["2026-11-16", "2026-11-18"]
    back = _search(
        destination="سنغافورة",
        depart={"kind": "weekday", "weekday": "mon", "which": "coming"},  # Monday 11-23
        return_date={"kind": "nights", "nights": 1},  # Tuesday 11-24
    )
    assert (back["status"], back["leg"]) == ("no_flights_that_day", "return")
    assert [d["iso"] for d in back["nearest"]] == ["2026-11-23", "2026-11-25"]


def test_a_day_the_code_chose_the_month_of_is_marked_to_be_said_back() -> None:
    found = _search(destination="Doha", depart={"kind": "on", "day": 17}, one_way=True)
    assert found["date"] == {
        "iso": "2026-11-17",
        "day": 17,
        "month": "November",
        "weekday": "Tuesday",
        "assumed": True,
    }


@pytest.mark.parametrize("tag", TAGS)
def test_a_search_that_does_not_answer_is_said_as_a_failure_never_as_no_flights(tag: Tag) -> None:
    trips = TripBook()
    tool = search_flights(airline(search_mode="fail"), trips)
    result = run(tool, tag, destination="London", depart=DEC_17, return_date=DEC_20)
    assert not result.ok and result.data == {"error": SEARCH_FAILED}
    assert result.card is None and len(trips) == 0
    assert "Do not say there are no flights or no seats." in SEARCH_FAILED


def test_a_raw_date_is_refused_with_its_field_named() -> None:
    tool = search_flights(airline(), TripBook())
    result = run(tool, destination="London", depart="2026-12-17")
    assert not result.ok and "`depart" in json.dumps(result.data)
    unknown = run(tool, destination="London", depart=DEC_17, city="London")
    assert not unknown.ok


def test_the_talker_sees_its_arguments_and_no_bound_one() -> None:
    tool = search_flights(airline(), TripBook())
    schema = tool.tool_schema()
    assert schema.name == SEARCH_FLIGHTS and tool.progress == "searching"
    assert tool.timeout_s == 5.0 and "never work out a date yourself" in schema.description
    properties = json.loads(json.dumps(dict(schema.parameters)))["properties"]
    assert set(properties) == {
        "destination",
        "origin",
        "depart",
        "return_date",
        "one_way",
        "travelers",
        "cabin",
    }
    assert dict(schema.parameters)["required"] == ["destination", "depart"]
