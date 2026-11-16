"""`compare_cabins`, run after a search in the same call: each cabin of the picked flight with
its fare and seats, first class marked not offered where the aircraft has none, the pick read as
`choose_flight` reads it, the draft left as it was, a read that does not answer said as a
failure, and the card passing the output guard's ID rule in every language."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from flight_voice.airline.fares import fare
from flight_voice.airline.schedule import departure, find_flight
from flight_voice.said import Tag
from flight_voice.tools.cabins import COMPARE_CABINS, compare_cabins
from flight_voice.tools.results import SAY, SEARCH_FAILED
from t2_agentic_voice import CardRow

from tests.flight_voice.scenario_dates import business_sold_out
from tests.flight_voice.tools.tool_support import (
    DEC_17,
    FIRST,
    TAGS,
    Call,
    card_passes,
    data,
    london,
    run,
)


def _compare(call: Call, choice: dict[str, Any], leg: str = "outbound") -> Any:
    return run(compare_cabins(call.airline, call.trips), call.tag, leg=leg, choice=choice)


def test_a_787_flight_has_all_three_cabins_with_their_fares() -> None:
    call = london()
    before = call.draft
    made = _compare(call, FIRST)
    found = data(made)
    assert (found["status"], found["say"], found["flight"]) == ("ok", SAY["cabins"], "T2 401")
    flight = find_flight(401)
    assert flight is not None
    flown = departure(flight, date(2026, 12, 17))
    fares = {c["cabin"]: c["fare_sar"] for c in found["cabins"]}
    assert fares == {c: fare(flown, c) for c in ("economy", "business", "first")}
    assert [c.get("current") for c in found["cabins"]] == [True, None, None]
    assert made.card is not None and made.card.title == "Cabins on flight T2 401, Thu 17 Dec"
    economy, business, first = made.card.rows
    assert economy == CardRow(title="Economy", value=f"{fares['economy']:,} SAR", mark="chosen")
    assert business == CardRow(title="Business class", value=f"{fares['business']:,} SAR")
    assert first.title == "First class" and first.mark is None and made.card.steps == ()
    assert call.draft == before and card_passes(made)


@pytest.mark.parametrize("tag", TAGS)
def test_first_class_is_marked_not_offered_on_an_aircraft_without_it(tag: Tag) -> None:
    call = Call(tag)
    call.search(destination="Dubai", depart=DEC_17, one_way=True)
    made = _compare(call, {"pick": "latest"})
    first = data(made)["cabins"][2]
    assert (first["cabin"], first["offered"]) == ("first", False)
    assert "fare_sar" not in first and "seats_ok" not in first
    assert made.card is not None and card_passes(made)
    missing = made.card.rows[2]
    assert missing.mark == "unavailable" and missing.value is None
    if tag == "en":
        assert missing == CardRow(
            title="First class", detail="not offered on an A321neo", mark="unavailable"
        )


def test_a_sold_out_cabin_is_said_full() -> None:
    sold_out = business_sold_out("RUH", "CAI")
    assert sold_out is not None
    number, day = sold_out
    call = Call()
    listed = call.search(
        destination="Cairo", depart={"kind": "on", "day": day.day, "month": day.month}, one_way=True
    )
    n = next(o["n"] for o in listed["options"] if o["flight"] == f"T2 {number}")
    made = _compare(call, {"pick": "number", "n": n})
    business = data(made)["cabins"][1]
    assert (business["cabin"], business["seats_ok"]) == ("business", False)
    assert made.card is not None and card_passes(made)
    full = made.card.rows[1]
    assert (full.title, full.detail, full.mark) == ("Business class", "full", "unavailable")


def test_a_flight_not_listed_or_not_clear_is_said_so() -> None:
    assert data(_compare(Call(), FIRST))["status"] == "nothing_listed"
    call = Call()
    call.search(destination="Jeddah", depart=DEC_17, one_way=True)
    unclear = data(_compare(call, {"pick": "part_of_day", "part": "morning"}))
    assert unclear["status"] == "unclear_choice" and len(unclear["options"]) == 2


def test_a_read_that_does_not_answer_is_said_as_a_failure() -> None:
    call = london()
    call.airline.search_mode = "fail"
    failed = _compare(call, FIRST)
    assert not failed.ok and failed.data == {"error": SEARCH_FAILED}


def test_the_talker_sees_the_leg_and_the_pick() -> None:
    schema = compare_cabins(Call().airline, Call().trips).tool_schema()
    assert schema.name == COMPARE_CABINS
    assert dict(schema.parameters)["required"] == ["leg", "choice"]
