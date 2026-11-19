"""The way back asked as a new search (flight_voice/lean/find_return.py's `as_return`): with the
trip's outbound chosen, A to B on day D, a one-way search B to A on a day on or after D is read
as the trip's return, the outbound's pick kept, the trip made a round trip, and the return's
flights listed to choose from; a round trip's return day moves the same way; never while the
outbound is not chosen, never for a day before D, and never for another route; an airline
asked then narrows the way back alone. The owner's call of 2026-11-19 played exactly: RUH to
DMM on 21 November on flynas, chosen one way, then DMM to RUH on the 25th, then the cheapest
return chosen: a round trip of both legs, its total their sum. The real network's alone: the
mock's search stays as run F reads it."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Final

from flight_voice.flight_data.model import Offer, Place
from flight_voice.lean.find_return import RETURN_ADDED

from tests.flight_voice.flight_data.fake import (
    FLYADEAL,
    FLYNAS,
    PLACES,
    RIYADH,
    SAUDIA,
    FakeFlightData,
    FakePlaces,
    answered,
    nonstop,
    query,
)
from tests.flight_voice.lean.lean_support import LeanCall, ids
from tests.flight_voice.lean.real_support import real_call
from tests.flight_voice.tools.tool_support import card_passes, data

DAMMAM: Final = Place(code="DMM", airports=("DMM",), city_en="Dammam", city_ar="الدمام")
OUT: Final = date(2026, 11, 21)
BACK: Final = date(2026, 11, 25)
LATER: Final = date(2026, 11, 27)
EARLIER: Final = date(2026, 11, 20)


def _at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0)


def _way(day: date, route: tuple[str, str], base: int) -> tuple[Offer, ...]:
    return (
        nonstop(FLYNAS, "121", route, _at(day, 7), 75, base),
        nonstop(SAUDIA, "1201", route, _at(day, 12), 75, base + 160),
        nonstop(FLYADEAL, "361", route, _at(day, 19), 75, base + 40),
    )


def _dammam() -> LeanCall:
    """A call on the real network with Riyadh and Dammam's days, each way."""
    data_ = FakeFlightData()
    for day, base in ((OUT, 289), (BACK, 310), (LATER, 260), (EARLIER, 300)):
        data_.set(answered(query(RIYADH, DAMMAM, day), _way(day, ("RUH", "DMM"), base)))
        data_.set(answered(query(DAMMAM, RIYADH, day), _way(day, ("DMM", "RUH"), base + 5)))
    deps = real_call(data_).deps
    return LeanCall("en", deps=replace(deps, places=FakePlaces((*PLACES, DAMMAM))))


def _flynas_out(call: LeanCall) -> str:
    found = call.find(destination="Dammam", depart=OUT.isoformat())
    chosen = next(o for o in data(found)["outbound"]["options"] if o["airline"] == "flynas")
    picked = data(call.choose(outbound_id=chosen["id"]))
    assert picked["trip"] == "one way" and picked["missing"] == []
    return str(chosen["id"])


def test_the_owners_call_ends_a_round_trip_with_both_legs_and_their_sum() -> None:
    call = _dammam()
    out_id = _flynas_out(call)
    back = call.find(origin="Dammam", destination="Riyadh", depart=BACK.isoformat())
    answer = data(back)
    assert answer["route"] == "Riyadh to Dammam" and answer["chosen"] == {"outbound": out_id}
    assert answer["return"]["day"]["date"] == BACK.isoformat()
    assert len(answer["return"]["options"]) == 3 and RETURN_ADDED in answer["note"]
    assert back.card is not None and back.card.slot == "return" and card_passes(back)
    assert [r.mark for r in back.card.rows][-1] == "chosen"  # the outbound kept beside them
    draft = call.draft
    assert not draft.one_way and draft.return_date == BACK and draft.depart == OUT
    assert draft.chosen_outbound is not None and draft.chosen_outbound.id == out_id
    cheapest = min(answer["return"]["options"], key=lambda o: o["price"])
    done = data(call.choose(return_id=cheapest["id"]))
    assert done["missing"] == [] and done["trip"] == "round trip"
    assert (done["outbound"]["id"], done["return"]["id"]) == (out_id, cheapest["id"])
    assert done["total"] == 289 + 315 == done["outbound"]["price"] + done["return"]["price"]


def test_a_round_trips_return_day_moves_the_same_way() -> None:
    call = _dammam()
    out_id = _flynas_out(call)
    call.find(origin="Dammam", destination="Riyadh", depart=BACK.isoformat())
    moved = data(call.find(origin="الدمام", destination="الرياض", depart=LATER.isoformat()))
    assert moved["chosen"] == {"outbound": out_id}
    assert moved["return"]["day"]["date"] == LATER.isoformat()
    assert call.draft.return_date == LATER and call.draft.chosen_outbound is not None


def test_a_search_back_is_a_new_trip_without_a_chosen_outbound_or_before_it() -> None:
    call = _dammam()
    call.find(destination="Dammam", depart=OUT.isoformat())  # listed, not chosen
    alone = data(call.find(origin="Dammam", destination="Riyadh", depart=BACK.isoformat()))
    assert alone["route"] == "Dammam to Riyadh" and "return" not in alone
    assert "note" not in alone or RETURN_ADDED not in alone["note"]
    chosen = _dammam()
    _flynas_out(chosen)
    before = data(chosen.find(origin="Dammam", destination="Riyadh", depart=EARLIER.isoformat()))
    assert before["route"] == "Dammam to Riyadh" and chosen.draft.chosen_outbound is None


def test_an_airline_asked_for_the_way_back_narrows_the_way_back_alone() -> None:
    # The review's probe: Saudia does not fly the outbound's day, only the way back.
    call = _dammam()
    source = call.deps.data
    assert isinstance(source, FakeFlightData)
    flown = tuple(o for o in _way(OUT, ("RUH", "DMM"), 289) if o.carrier != SAUDIA)
    source.set(answered(query(RIYADH, DAMMAM, OUT), flown))
    out_id = _flynas_out(call)
    back = call.find(
        origin="Dammam", destination="Riyadh", depart=BACK.isoformat(), airline="Saudia"
    )
    answer = data(back)
    assert answer["chosen"] == {"outbound": out_id} and RETURN_ADDED in answer["note"]
    assert [o["airline"] for o in answer["return"]["options"]] == ["Saudia"]
    assert out_id in {o["id"] for o in answer["outbound"]["options"]}  # the outbound left whole
    assert back.card is not None and back.card.slot == "return" and card_passes(back)
    assert back.card.rows[-1].mark == "chosen"  # flynas's pick beside Saudia's way back
    assert call.draft.listed_outbound is not None and call.draft.listed_outbound.airline is None


def test_an_airline_that_does_not_fly_the_way_back_is_said_and_the_trip_kept() -> None:
    call = _dammam()
    out_id = _flynas_out(call)
    asked = call.find(
        origin="Dammam", destination="Riyadh", depart=BACK.isoformat(), airline="Emirates"
    )
    answer = data(asked)
    assert answer == {
        "status": "no_flights_for_airline",
        "airline": "Emirates",
        "airlines": ["flynas", "Saudia", "flyadeal"],  # the way back's, DMM to RUH
    }
    draft = call.draft
    assert (
        draft.one_way and draft.chosen_outbound is not None and draft.chosen_outbound.id == out_id
    )


def test_the_mock_keeps_its_search_as_run_f_reads_it() -> None:
    # Run F plays the mock: its way back searched alone stays a new trip, as before round 2.
    call = LeanCall()
    out = ids(call.find(destination="Jeddah", depart="2026-11-19"))[0]
    call.choose(outbound_id=out)
    answer = data(call.find(origin="Jeddah", destination="Riyadh", depart="2026-11-21"))
    assert answer["route"] == "Jeddah to Riyadh" and "chosen" not in answer
    assert "return" not in answer and call.draft.chosen_outbound is None
    # A round trip searched again with its outbound's pick kept: the outbound's card, as before.
    trip = LeanCall()
    first = ids(trip.find(destination="Jeddah", depart="2026-11-19", return_date="2026-11-21"))
    trip.choose(outbound_id=first[0])
    again = trip.find(destination="Jeddah", depart="2026-11-19", return_date="2026-11-21")
    assert data(again)["chosen"] == {"outbound": first[0]} and data(again)["return"]["count"] == 4
    assert again.card is not None and again.card.slot == "outbound"
