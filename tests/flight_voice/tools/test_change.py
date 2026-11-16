"""`change_trip` and `get_trip`, run as the talker's call would run them: a change prices the
chosen legs again, a leg short of seats in the new cabin loses its choice and its flights are
listed again, a complete trip goes straight to `book_trip`, a cabin the route does not sell is
refused, a call with nothing to change is told so; and the trip as the talker reads it, with the
card of each passing the output guard's ID rule."""

from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

import pytest
from flight_voice.airline.fares import round10
from flight_voice.said import Tag
from flight_voice.tools import cards
from flight_voice.tools.choose import CHANGE_TRIP, NOTHING_TO_CHANGE, change_trip
from flight_voice.tools.results import SAY
from flight_voice.tools.trip_view import GET_TRIP, get_trip

from tests.flight_voice.scenario_dates import TODAY, business_sold_out
from tests.flight_voice.tools.tool_support import (
    CHEAPEST,
    DEC_17,
    DEC_20,
    FIRST,
    TAGS,
    Call,
    card_passes,
    data,
    london,
    run,
)


def _change(call: Call, **arguments: Any) -> Any:
    return run(change_trip(call.airline, call.trips), call.tag, **arguments)


def _trip(call: Call) -> Any:
    return run(get_trip(call.airline, call.trips), call.tag)


def _complete(tag: Tag = "en") -> Call:
    call = london(tag)
    call.choose("outbound", FIRST)
    call.choose("return", CHEAPEST)
    return call


def test_more_travelers_on_a_complete_trip_price_it_again_and_send_it_to_book() -> None:
    call = _complete()
    one = call.draft.total(TODAY)
    changed = _change(call, travelers=2)
    found = data(changed)
    assert (found["changed"], found["say"]) == (["travelers"], SAY["complete"])
    assert found["trip"]["travelers"] == 2 and found["trip"]["total_sar"] == 2 * (one or 0)
    assert call.draft.travelers == 2 and card_passes(changed)
    assert changed.card is not None
    assert "2 travelers in economy" in [row.title for row in changed.card.rows]


def test_a_cabin_the_chosen_flight_has_no_seat_in_drops_that_leg_and_lists_it_again() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    call = Call()
    on = {"kind": "on", "day": day.day, "month": day.month}
    listed = call.search(destination="Cairo", depart=on, one_way=True)
    n = next(o["n"] for o in listed["options"] if o["flight"] == f"T2 {number}")
    call.choose("outbound", {"pick": "number", "n": n})
    found = data(_change(call, cabin="business"))
    assert (found["lost"], found["leg"], found["say"]) == (
        ["outbound"],
        "outbound",
        SAY["changed_lost"],
    )
    by_flight = {o["flight"]: o for o in found["options"]}
    assert by_flight[f"T2 {number}"]["seats_ok"] is False
    assert call.draft.chosen_outbound is None and call.draft.cabin == "business"
    assert found["trip"]["missing"] == ["outbound"]


def test_a_cabin_change_while_choosing_lists_the_flights_again_with_their_new_fares() -> None:
    call = Call()
    economy = call.search(destination="London", depart=DEC_17, return_date=DEC_20)
    found = data(_change(call, cabin="business"))
    assert (found["leg"], found["say"]) == ("outbound", SAY["changed_relist"])
    fares = [o["fare_sar"] for o in found["options"]]
    assert fares == [round10(o["fare_sar"] * Fraction("3.2")) for o in economy["options"]]
    assert found["trip"]["cabin"] == "business" and call.draft.cabin == "business"


def test_one_way_on_a_round_trip_drops_the_return_and_completes_the_trip() -> None:
    call = london()
    call.choose("outbound", FIRST)
    found = data(_change(call, one_way=True))
    assert found["say"] == SAY["complete"] and found["trip"]["trip_kind_said"] == "one way"
    assert call.draft.one_way and call.draft.return_date is None
    assert call.draft.shown_return == ()


def test_a_round_trip_again_asks_when_they_come_back() -> None:
    call = Call()
    call.search(destination="Dubai", depart=DEC_17, one_way=True)
    call.choose("outbound", FIRST)
    found = data(_change(call, one_way=False))
    assert found["say"] == SAY["changed_needs_return"]
    assert found["trip"]["missing"] == ["return_date", "return"]


def test_a_change_before_any_search_keeps_it_for_the_search() -> None:
    call = Call()
    found = data(_change(call, travelers=3))
    assert found["say"] == SAY["changed"] and call.draft.travelers == 3
    listed = call.search(destination="Doha", depart=DEC_17, one_way=True)
    assert listed["travelers"] == 3


def test_a_cabin_the_route_does_not_sell_is_refused_and_changes_nothing() -> None:
    call = london()
    call.search(destination="Dubai", depart=DEC_17, one_way=True)
    before = call.draft
    found = data(_change(call, cabin="first"))
    assert (found["status"], found["offered"]) == ("cabin_not_offered", ["economy", "business"])
    assert call.draft == before


def test_a_change_of_nothing_is_told_back_as_a_failure() -> None:
    call = london()
    refused = _change(call)
    assert not refused.ok and refused.data == {"error": NOTHING_TO_CHANGE}
    assert not _change(call, travelers=10).ok


def test_the_trip_read_before_anything_is_planned_asks_where_to() -> None:
    read = _trip(Call())
    found = data(read)
    assert (found["status"], found["say"]) == ("empty", SAY["trip_empty"])
    assert read.card is None


@pytest.mark.parametrize("tag", TAGS)
def test_the_trip_read_gives_what_is_chosen_and_what_is_missing(tag: Tag) -> None:
    call = london(tag)
    early = data(_trip(call))
    assert early["missing"] == ["outbound", "return"] and early["say"] == SAY["trip"]
    assert early["depart"]["iso"] == "2026-12-17" and "outbound" not in early
    call.choose("outbound", FIRST)
    call.choose("return", CHEAPEST)
    read = _trip(call)
    found = data(read)
    assert found["missing"] == [] and found["total_sar"] == call.draft.total(TODAY)
    assert read.card is not None and card_passes(read)
    if tag == "ar-SA":
        assert (found["trip_kind_said"], found["trip_kind_said_msa"]) == ("رايح جاي", "ذهاب وعودة")
        assert found["route_said"] == "من الرياض للندن"


@pytest.mark.parametrize(
    ("travelers", "english", "arabic"),
    [
        (1, "1 traveler in economy", "مسافر واحد في الدرجة السياحية"),
        (2, "2 travelers in economy", "مسافران في الدرجة السياحية"),
        (3, "3 travelers in economy", "٣ مسافرين في الدرجة السياحية"),
    ],
)
def test_the_travelers_on_a_card(travelers: int, english: str, arabic: str) -> None:
    assert cards.party(travelers, "economy", "en") == english
    assert cards.party(travelers, "economy", "ar-SA") == arabic


def test_the_talker_sees_the_changes_it_may_pass_and_no_argument_to_read_the_trip() -> None:
    call = Call()
    change = change_trip(call.airline, call.trips).tool_schema()
    assert change.name == CHANGE_TRIP
    assert set(json.loads(json.dumps(dict(change.parameters)))["properties"]) == {
        "travelers",
        "cabin",
        "one_way",
    }
    read = get_trip(call.airline, call.trips).tool_schema()
    assert read.name == GET_TRIP and dict(read.parameters).get("properties", {}) == {}
