"""The lean agent's `find_flights` (flight_voice/lean/find.py, span.py), run through the
library's own runner: the outbound day's flights as plain data (stable ids, times, fares, seats,
the count, the first and last times, the cheapest) and a round trip's return by its day alone,
its flights listed in the trip for choose_flights; a search that keeps a pick names it, with the
return's flights once the outbound is chosen; the trip written and one way with no return,
the route and the fares' basis in the caller's register, the basis with no digit word beside a
fare, the outbound card; a span of days with each day's count and
lowest fare, the two cheapest days and its calendar card, nothing written; and each refusal as
data: a route not served, a day past or past the window, a span too long, a return before its
departure, a cabin not sold, a day with no flight, a full flight's note, and a failed search."""

from __future__ import annotations

from typing import Any

from flight_voice.lean.find_return import RETURN_KEPT, RETURN_LISTED
from flight_voice.lean.results import EACH_WAY, PER_PERSON

from tests.flight_voice.lean.lean_support import BACK, OUT, LeanCall, chosen_trip, ids
from tests.flight_voice.tools.tool_support import airline, card_passes, data, ids_pass


def test_a_day_lists_the_outbound_as_plain_data_and_writes_the_trip() -> None:
    call = LeanCall()
    found = call.find(destination="Jeddah", depart=OUT, return_date=BACK)
    answer = data(found)
    assert answer["status"] == "ok" and answer["fares_are"] == EACH_WAY
    assert answer["route"] == "Riyadh to Jeddah" and "say" not in answer
    out, back = answer["outbound"], answer["return"]
    assert out["day"] == {"date": OUT, "weekday": "Thursday"}
    assert out["count"] == 4 and (out["first_departs"], out["last_departs"]) == ("06:00", "21:00")
    first = out["options"][0]
    assert first["id"] == "T2101-2026-11-19" and first["stops"] == 0
    assert first["airline"] == "T2 Air" and first["flight"] == "T2 101"
    assert set(first) >= {"departs", "arrives", "duration", "price", "seats_ok", "part_of_day"}
    assert "via" not in first and "airlines" not in out and "more" not in out
    cheapest = min((o for o in out["options"] if o["seats_ok"]), key=lambda o: o["price"])
    assert out["cheapest_id"] == cheapest["id"]
    # f-dev-lean-4: given both days' flights, the model listed both in one reply (34 of 38) and
    # took one pick for both legs (f30, f09); the return's flights come with choose_flights.
    assert back == {"day": {"date": BACK, "weekday": "Saturday"}, "note": RETURN_LISTED}
    assert "T2102" not in str(answer)
    assert found.card is not None and found.card.slot == "outbound" and card_passes(found)
    draft = call.draft
    assert draft.destination is not None and draft.destination.code == "JED"
    assert (draft.one_way, str(draft.return_date)) == (False, BACK)
    assert draft.listed_outbound is not None and draft.listed_return is not None
    assert [o.flights for o in draft.listed_outbound.offers] == [
        ("T2 101",),
        ("T2 103",),
        ("T2 105",),
        ("T2 107",),
    ]
    assert [o.segments[0].number for o in draft.listed_return.offers] == [
        "102",
        "104",
        "106",
        "108",
    ]


def test_a_new_return_day_after_the_outbound_pick_keeps_it_and_lists_the_return() -> None:
    # The caller picked the way out, then moved the way back a day: the pick is named as kept,
    # and the new day's flights are given, so the way out is never asked again.
    call = LeanCall()
    out = ids(call.find(destination="Jeddah", depart=OUT, return_date=BACK))[0]
    call.choose(outbound_id=out)
    answer = data(call.find(destination="Jeddah", depart=OUT, return_date="2026-11-22"))
    assert answer["chosen"] == {"outbound": out} and "note" not in answer["return"]
    assert answer["return"]["day"]["date"] == "2026-11-22" and answer["return"]["count"] == 4
    assert call.draft.chosen_outbound is not None and call.draft.chosen_return is None


def test_a_new_outbound_day_after_both_picks_keeps_the_returns() -> None:
    call = chosen_trip()  # out on T2 101, back on T2 102
    answer = data(call.find(destination="Jeddah", depart="2026-11-20", return_date=BACK))
    assert answer["chosen"] == {"return": "T2102-2026-11-21"} and "lost" not in answer
    assert answer["return"] == {"day": {"date": BACK, "weekday": "Saturday"}, "note": RETURN_KEPT}
    assert "chosen" not in data(LeanCall().find(destination="Jeddah", depart=OUT))


def test_no_return_makes_the_trip_one_way_and_lists_the_outbound_alone() -> None:
    call = LeanCall()
    answer = data(call.find(destination="JED", depart=OUT))
    assert "return" not in answer and call.draft.one_way
    assert answer["fares_are"] == PER_PERSON and "fares_are_msa" not in answer


def test_a_fare_said_with_its_basis_passes_the_id_rule() -> None:
    # f-dev-lean-3, f07: "a fare of 910, one-way per person" read as 9101, and the reply
    # blocked whole; the basis holds no digit word, so the fare said beside it passes.
    for depart in ({"depart": OUT, "return_date": BACK}, {"depart": OUT}):
        found = LeanCall().find(destination="Jeddah", **depart)
        answer = data(found)
        fare = answer["outbound"]["options"][0]["price"]
        said = f"The cheapest leaves at 06:00 with a fare of {fare}, {answer['fares_are']}."
        assert ids_pass([said], found.texts()), said


def test_a_saudi_reply_gets_its_route_in_saudi_and_in_msa() -> None:
    answer = data(LeanCall("ar-SA").find(destination="جدة", depart=OUT))
    assert answer["route"] == "من الرياض لجدة" and answer["route_msa"] == "من الرياض إلى جدة"
    assert answer["outbound"]["day"]["weekday"] == "الخميس"
    # Its MSA form too, so an MSA caller is never given the Saudi phrase (f-dev-lean-3, f03).
    assert answer["fares_are"] == "للشخص، رايح بس"
    assert answer["fares_are_msa"] == "للشخص، ذهاب فقط"


def test_a_span_gives_each_day_and_the_two_cheapest_and_writes_nothing() -> None:
    call = LeanCall()
    found = call.find(destination="Singapore", depart={"first": "2026-11-16", "last": "2026-11-22"})
    answer = data(found)
    assert answer["status"] == "days" and answer["fares_are"] == PER_PERSON
    assert [d["date"] for d in answer["no_flight_days"]] == ["2026-11-17"]  # a Tuesday
    assert len(answer["days"]) == 6 and all(d["flights"] >= 1 for d in answer["days"])
    lowest = sorted(answer["days"], key=lambda d: (d["lowest_price"], d["date"]))[:2]
    assert answer["cheapest_days"] == [d["date"] for d in lowest]
    assert answer["departs"] and all(":" in t for t in answer["departs"])
    assert found.card is not None and found.card.slot == "outbound" and card_passes(found)
    assert len(found.card.rows) == 7
    assert call.draft.destination is None


def test_a_one_day_span_lists_that_days_flights_to_choose() -> None:
    # The owner's call of 2026-11-18: a span of one day gave no flight id, so nothing to book.
    call = LeanCall()
    answer = data(call.find(destination="Jeddah", depart={"first": OUT, "last": OUT}))
    assert answer["status"] == "ok" and answer["outbound"]["day"]["date"] == OUT
    first = answer["outbound"]["options"][0]["id"]
    assert data(call.choose(outbound_id=first))["status"] == "ok"
    span = data(call.find(destination="Singapore", depart={"first": OUT, "last": "2026-11-22"}))
    assert "find_flights" in span["note"]  # how to book one of its days


def test_a_long_span_shows_its_cheapest_days_on_the_card() -> None:
    found = LeanCall().find(
        destination="Dubai", depart={"first": "2026-11-20", "last": "2026-12-03"}
    )
    assert len(data(found)["days"]) == 14
    assert found.card is not None and len(found.card.rows) == 8


def test_a_span_past_two_weeks_is_given_week_by_week() -> None:
    found = LeanCall().find(
        destination="Dubai", depart={"first": "2026-11-20", "last": "2026-12-19"}
    )
    answer = data(found)
    assert answer["days"] == [] and answer["no_flight_days"] == []
    weeks = answer["weeks"]
    assert len(weeks) == 5 and weeks[0]["first"]["date"] == "2026-11-20"
    assert weeks[0]["last"]["date"] == "2026-11-21"  # Friday and Saturday end the Saudi week
    assert weeks[1]["first"]["date"] == "2026-11-22" and weeks[-1]["last"]["date"] == "2026-12-19"
    for week in weeks:
        assert 1 <= week["days_with_flights"] <= 7
        assert week["first"]["date"] <= week["cheapest"]["date"] <= week["last"]["date"]
    lowest = sorted((w["cheapest"] for w in weeks), key=lambda d: (d["lowest_price"], d["date"]))
    assert answer["cheapest"][0] == lowest[0] and len(answer["cheapest"]) == 2
    assert answer["cheapest_days"] == [d["date"] for d in answer["cheapest"]]
    # The card: each week's cheapest day, the two cheapest marked, no day the result lacks.
    assert found.card is not None and len(found.card.rows) == 5 and card_passes(found)
    assert sum(r.mark == "best" for r in found.card.rows) == 2


def test_two_months_is_the_longest_span() -> None:
    answer = data(
        LeanCall().find(destination="Dubai", depart={"first": "2026-11-20", "last": "2027-01-20"})
    )
    assert answer["status"] == "days" and len(answer["weeks"]) == 10


def test_each_date_the_window_refuses_names_the_window() -> None:
    call = LeanCall()
    cases: dict[str, dict[str, Any]] = {
        "past": {"depart": "2026-11-15"},
        "beyond_window": {"depart": "2027-03-17"},
        "return_before_departure": {"depart": OUT, "return_date": "2026-11-18"},
        "span_too_long": {"depart": {"first": "2026-11-20", "last": "2027-01-21"}},
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
