"""The lean agent's `find_flights` (flight_voice/lean/find.py, span.py), run through the
library's own runner: a day's flights each way as plain data (stable ids, times, fares, seats,
the count, the first and last times, the cheapest), the trip written and one way with no return,
the route in the caller's register, the outbound card; a span of days with each day's count and
lowest fare, the two cheapest days and its calendar card, nothing written; and each refusal as
data: a route not served, a day past or past the window, a span too long, a return before its
departure, a cabin not sold, a day with no flight, a full flight's note, and a failed search."""

from __future__ import annotations

from typing import Any

from flight_voice.lean.results import FARES_ARE

from tests.flight_voice.lean.lean_support import BACK, OUT, LeanCall, ids
from tests.flight_voice.tools.tool_support import airline, card_passes, data


def test_a_day_lists_each_way_as_plain_data_and_writes_the_trip() -> None:
    call = LeanCall()
    found = call.find(destination="Jeddah", depart=OUT, return_date=BACK)
    answer = data(found)
    assert answer["status"] == "ok" and answer["fares_are"] == FARES_ARE
    assert answer["route"] == "Riyadh to Jeddah" and "say" not in answer
    out, back = answer["outbound"], answer["return"]
    assert out["day"] == {"date": OUT, "weekday": "Thursday"}
    assert out["count"] == 4 and (out["first_departs"], out["last_departs"]) == ("06:00", "21:00")
    first = out["options"][0]
    assert first["id"] == "T2-101-2026-11-19" and first["nonstop"] is True
    assert set(first) >= {"departs", "arrives", "duration", "fare", "seats_ok", "part_of_day"}
    cheapest = min((o for o in out["options"] if o["seats_ok"]), key=lambda o: o["fare"])
    assert out["cheapest_id"] == cheapest["id"]
    assert back["day"]["date"] == BACK and ids(found, "return")[0] == "T2-102-2026-11-21"
    assert found.card is not None and found.card.slot == "outbound" and card_passes(found)
    draft = call.draft
    assert (draft.destination, draft.one_way, str(draft.return_date)) == ("JED", False, BACK)
    assert [s.flight for s in draft.shown_outbound] == [101, 103, 105, 107]
    assert [s.flight for s in draft.shown_return] == [102, 104, 106, 108]


def test_no_return_makes_the_trip_one_way_and_lists_the_outbound_alone() -> None:
    call = LeanCall()
    answer = data(call.find(destination="JED", depart=OUT))
    assert "return" not in answer and call.draft.one_way


def test_a_saudi_reply_gets_its_route_in_saudi_and_in_msa() -> None:
    answer = data(LeanCall("ar-SA").find(destination="جدة", depart=OUT))
    assert answer["route"] == "من الرياض لجدة" and answer["route_msa"] == "من الرياض إلى جدة"
    assert answer["outbound"]["day"]["weekday"] == "الخميس"


def test_a_span_gives_each_day_and_the_two_cheapest_and_writes_nothing() -> None:
    call = LeanCall()
    found = call.find(destination="Singapore", depart={"first": "2026-11-16", "last": "2026-11-22"})
    answer = data(found)
    assert answer["status"] == "days" and answer["fares_are"] == FARES_ARE
    assert [d["date"] for d in answer["no_flight_days"]] == ["2026-11-17"]  # a Tuesday
    assert len(answer["days"]) == 6 and all(d["flights"] >= 1 for d in answer["days"])
    lowest = sorted(answer["days"], key=lambda d: (d["lowest_fare"], d["date"]))[:2]
    assert answer["cheapest_days"] == [d["date"] for d in lowest]
    assert answer["departs"] and all(":" in t for t in answer["departs"])
    assert found.card is not None and found.card.slot == "outbound" and card_passes(found)
    assert len(found.card.rows) == 7
    assert call.draft.destination is None


def test_a_long_span_shows_its_cheapest_days_on_the_card() -> None:
    found = LeanCall().find(
        destination="Dubai", depart={"first": "2026-11-20", "last": "2026-12-03"}
    )
    assert len(data(found)["days"]) == 14
    assert found.card is not None and len(found.card.rows) == 8


def test_each_date_the_window_refuses_names_the_window() -> None:
    call = LeanCall()
    cases: dict[str, dict[str, Any]] = {
        "past": {"depart": "2026-11-15"},
        "beyond_window": {"depart": "2027-03-17"},
        "return_before_departure": {"depart": OUT, "return_date": "2026-11-18"},
        "span_too_long": {"depart": {"first": "2026-11-20", "last": "2026-12-04"}},
    }
    for problem, dates in cases.items():
        answer = data(call.find(destination="Jeddah", **dates))
        assert answer["status"] == "date_problem" and answer["problem"] == problem
        assert (answer["first_day"], answer["last_day"]) == ("2026-11-16", "2027-03-16")
        assert answer["note"]
    assert call.draft.destination is None


def test_a_route_not_served_gives_the_cities_served() -> None:
    for where in ({"destination": "Qassim"}, {"destination": "Dubai", "origin": "Jeddah"}):
        answer = data(LeanCall().find(depart=OUT, **where))
        assert answer["status"] == "not_served" and "London" in answer["served"]
        assert answer["note"] == "Every flight starts or ends in Riyadh."


def test_a_cabin_not_sold_on_the_route_names_those_that_are() -> None:
    answer = data(LeanCall().find(destination="Jeddah", depart=OUT, cabin="first"))
    assert answer == {
        "status": "cabin_not_offered",
        "cabin": "first",
        "offered": ["economy", "business"],
    }


def test_a_day_with_no_flight_gives_the_nearest_days_with_one() -> None:
    answer = data(LeanCall().find(destination="Singapore", depart="2026-11-17"))
    assert answer["status"] == "no_flights" and answer["day"] == "2026-11-17"
    assert [d["date"] for d in answer["nearest"]] == ["2026-11-16", "2026-11-18"]


def test_a_full_flight_is_noted_and_never_the_cheapest() -> None:
    answer = data(LeanCall().find(destination="London", depart=OUT, cabin="first", travelers=9))
    assert all(not o["seats_ok"] for o in answer["outbound"]["options"])
    assert "cheapest_id" not in answer["outbound"] and "seats_ok false" in answer["note"]


def test_a_search_that_does_not_answer_fails_and_writes_nothing() -> None:
    call = LeanCall(flights=airline(search_mode="fail"))
    found = call.find(destination="Jeddah", depart=OUT)
    assert not found.ok and "could not check flights" in str(found.data)
    assert call.draft.destination is None
