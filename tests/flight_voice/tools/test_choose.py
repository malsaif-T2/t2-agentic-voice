"""`choose_flight`, run as the talker's call would run it, after a search in the same call: the
outbound pick lists the return day's flights; the last pick gives the trip whole, its total
priced in code, and the `say` that sends the talker straight to `book_trip`; nothing listed, an
unclear pick and a full flight each have their status, and leave the draft as it was; a search
that does not answer is said as a failure; and every card passes the output guard's ID rule."""

from __future__ import annotations

import json
from datetime import date

import pytest
from flight_voice.airline.bookings import Leg, priced
from flight_voice.airline.schedule import Flight, departures
from flight_voice.said import Tag
from flight_voice.tools.choose import CHOOSE_FLIGHT, choose_flight
from flight_voice.tools.results import SAY, SEARCH_FAILED
from flight_voice.trip import Shown, TripBook, TripDraft

from tests.flight_voice.scenario_dates import TODAY, business_sold_out, cheapest_departs_last
from tests.flight_voice.tools.tool_support import (
    CALL_ID,
    CHEAPEST,
    DEC_17,
    FIRST,
    TAGS,
    Call,
    airline,
    card_passes,
    data,
    london,
    run,
)


def test_the_outbound_pick_lists_the_return_flights_and_the_draft_holds_both() -> None:
    call = london()
    chosen = call.choose("outbound", FIRST)
    found = data(chosen)
    assert (found["status"], found["leg"], found["say"]) == (
        "ok",
        "outbound",
        SAY["chosen_then_return"],
    )
    assert found["trip"]["outbound"]["flight"] == "T2 401"
    assert found["trip"]["missing"] == ["return"] and "total_sar" not in found["trip"]
    returns = found["returns"]
    assert (returns["leg"], returns["route_said"], returns["date"]["iso"]) == (
        "return",
        "London to Riyadh",
        "2026-12-20",
    )
    assert [o["departs"] for o in returns["options"]] == ["16:00", "21:45"]
    assert returns["fare_basis_said"] == "per person, one way"
    draft = call.draft
    assert draft.chosen_outbound == Leg(flight=401, day=date(2026, 12, 17))
    assert [s.flight for s in draft.shown_return] == [402, 404]
    assert chosen.card is not None and chosen.card.title == "London to Riyadh, Sun 20 Dec"
    assert card_passes(chosen)


@pytest.mark.parametrize("tag", TAGS)
def test_the_last_pick_gives_the_trip_whole_and_sends_the_talker_to_book_it(tag: Tag) -> None:
    call = london(tag)
    call.choose("outbound", FIRST)
    done = call.choose("return", CHEAPEST)
    found = data(done)
    assert (found["leg"], found["say"]) == ("return", SAY["complete"])
    assert "book_trip" in found["say"] and "returns" not in found
    trip = found["trip"]
    expected = priced(call.draft.legs(), "economy", 1, TODAY)
    assert trip["missing"] == [] and trip["total_sar"] == expected
    assert "mark" not in trip["outbound"] and "mark" not in trip["return_flight"]
    assert done.card is not None and len(done.card.steps) == 4 and card_passes(done)
    total = f"{expected:,}"
    if tag == "en":
        assert done.card.title == "Your trip"
        assert done.card.steps[0].startswith("Riyadh to London, Thu 17 Dec: 09:10 to 13:15")
        assert done.card.steps[2:] == ("1 traveler in economy", f"Total {total} SAR")
    else:
        assert done.card.title == "رحلتك" and done.card.steps[2] == "مسافر واحد في الدرجة السياحية"
        assert done.card.steps[3].startswith("المجموع ")


def test_a_one_way_trip_is_complete_at_its_one_pick() -> None:
    call = Call()
    call.search(destination="Dubai", depart=DEC_17, one_way=True)
    found = data(call.choose("outbound", {"pick": "time", "departs": "13:40"}))
    assert found["say"] == SAY["complete"] and found["trip"]["trip_kind_said"] == "one way"
    assert "return_flight" not in found["trip"] and call.draft.legs() == (
        Leg(flight=203, day=date(2026, 12, 17)),
    )


def test_a_pick_for_a_leg_with_nothing_listed_says_search_first() -> None:
    call = Call()
    found = data(call.choose("outbound", FIRST))
    assert (found["status"], found["say"]) == ("nothing_listed", SAY["nothing_listed"])
    assert len(call.trips) == 0
    listed = london()
    assert data(listed.choose("return", FIRST))["status"] == "nothing_listed"


def test_a_pick_that_names_two_flights_gives_both_back_and_chooses_none() -> None:
    call = Call()
    call.search(destination="Jeddah", depart=DEC_17, one_way=True)
    before = call.draft
    found = data(call.choose("outbound", {"pick": "part_of_day", "part": "morning"}))
    assert (found["status"], found["say"]) == ("unclear_choice", SAY["unclear_choice"])
    assert [(o["n"], o["departs"]) for o in found["options"]] == [(1, "06:00"), (2, "10:30")]
    assert call.draft == before


def test_a_pick_that_names_none_gives_every_option_listed() -> None:
    call = london()
    found = data(call.choose("outbound", {"pick": "number", "n": 4}))
    assert found["status"] == "unclear_choice"
    assert [o["n"] for o in found["options"]] == [1, 2]
    assert sum(1 for o in found["options"] if o.get("mark") == "cheapest") == 1


def test_a_picked_flight_short_of_seats_offers_the_cabins_and_flights_that_have_them() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    call = Call()
    on = {"kind": "on", "day": day.day, "month": day.month}
    listed = call.search(destination="Cairo", depart=on, one_way=True, cabin="business")
    n = next(o["n"] for o in listed["options"] if o["flight"] == f"T2 {number}")
    before = call.draft
    found = data(call.choose("outbound", {"pick": "number", "n": n}))
    assert (found["status"], found["say"]) == ("no_seats", SAY["no_seats_flight"])
    assert found["cabins_with_seats"] == ["economy"] and found["cabin"] == "business"
    assert all(o["seats_ok"] for o in found["other_flights"])
    assert all(o["flight"] != f"T2 {number}" for o in found["other_flights"])
    assert call.draft == before


def test_a_return_chosen_before_the_outbound_asks_for_the_outbound() -> None:
    call = Call()
    shown = (Shown(n=1, flight=402, day=date(2026, 12, 20)),)
    draft = TripDraft(
        destination="LHR",
        depart=date(2026, 12, 17),
        return_date=date(2026, 12, 20),
        shown_outbound=(Shown(n=1, flight=401, day=date(2026, 12, 17)),),
        shown_return=shown,
    )
    call.trips.put(CALL_ID, draft)
    found = data(call.choose("return", FIRST))
    assert found["say"] == SAY["chosen_then_outbound"] and found["trip"]["missing"] == ["outbound"]


def test_an_outbound_pick_on_a_round_trip_with_no_return_day_asks_for_it() -> None:
    call = Call()
    draft = TripDraft(
        destination="LHR",
        depart=date(2026, 12, 17),
        shown_outbound=(Shown(n=1, flight=401, day=date(2026, 12, 17)),),
    )
    call.trips.put(CALL_ID, draft)
    found = data(call.choose("outbound", FIRST))
    assert found["say"] == SAY["chosen_needs_return"]
    assert call.draft.chosen_outbound is not None


def test_the_third_one_is_the_third_said_when_the_cheapest_leaves_last() -> None:
    """Both legs of a Jeddah trip whose cheapest flight leaves last: «الثالثة» picks the third
    flight said, the cheapest, never the flight left out."""
    out, back = cheapest_departs_last("RUH", "JED"), cheapest_departs_last("JED", "RUH")
    assert out is not None and back is not None
    call = Call("ar-SA")
    call.search(
        destination="جدة",
        depart={"kind": "on", "day": out.day, "month": out.month},
        return_date={"kind": "on", "day": back.day, "month": back.month},
    )
    third = {"pick": "number", "n": 3}
    returns = data(call.choose("outbound", third))["returns"]
    assert [o["departs"] for o in returns["options"]] == ["07:45", "12:30", "23:00", "17:15"]
    assert returns["options"][2]["mark"] == "cheapest"
    assert call.choose("return", third).ok
    late = {(d.origin, d.departs.strftime("%H:%M")): d.number for d in _flights(out, back)}
    assert call.draft.chosen_outbound == Leg(flight=late[("RUH", "21:00")], day=out)
    assert call.draft.chosen_return == Leg(flight=late[("JED", "23:00")], day=back)


def test_a_return_listing_that_does_not_answer_is_a_failure_and_changes_nothing() -> None:
    call = london()
    before = call.draft
    call.airline.search_mode = "fail"
    failed = call.choose("outbound", FIRST)
    assert not failed.ok and failed.data == {"error": SEARCH_FAILED}
    assert call.draft == before


def test_the_talker_sees_the_leg_and_the_pick_and_nothing_bound() -> None:
    tool = choose_flight(airline(), TripBook())
    schema = tool.tool_schema()
    assert schema.name == CHOOSE_FLIGHT and "as they said it" in schema.description
    assert set(json.loads(json.dumps(dict(schema.parameters)))["properties"]) == {"leg", "choice"}
    assert dict(schema.parameters)["required"] == ["leg", "choice"]
    refused = run(tool, leg="outbound", choice={"pick": "flight", "number": 401})
    assert not refused.ok and "choice" in str(refused.data)


def _flights(out: date, back: date) -> list[Flight]:
    there = [d.flight for d in departures("RUH", "JED", out)]
    return there + [d.flight for d in departures("JED", "RUH", back)]
