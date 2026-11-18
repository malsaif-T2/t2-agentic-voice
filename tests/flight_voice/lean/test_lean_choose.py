"""The lean agent's `choose_flights` (flight_voice/lean/choose.py): the picks the model resolved,
by id, give the trip so far (each leg's day, times, length, nonstop and fare, as `book_trip`
gives them back too, what is missing, the first of it listed again, one leg at a time, and
the total once complete), the return segment's card with the outbound pick kept beside it, then
the review card; a changed traveler count or cabin prices the trip again, and a leg it leaves
with no seats is lost by its departure time and listed again; it says it books nothing; and each
refusal, written nowhere: nothing listed yet, an id not listed, a flight with no seats, a cabin
not sold."""

from __future__ import annotations

from typing import Any

from flight_voice.lean.choose import DESCRIPTION, NOTHING_LISTED, chosen_legs
from flight_voice.lean.results import option_id
from flight_voice.tools.cards import TRIP_EN

from tests.flight_voice.lean.lean_support import BACK, OUT, LeanCall, chosen_trip, ids
from tests.flight_voice.tools.tool_support import card_passes, data


def _found(call: LeanCall) -> tuple[list[str], list[str]]:
    """The outbound's ids find_flights gave, and the return's the trip lists, which
    choose_flights gives once the outbound is chosen."""
    listed = call.find(destination="Jeddah", depart=OUT, return_date=BACK)
    code = call.airline.code
    return ids(listed), [option_id(code, s.flight, s.day) for s in call.draft.shown_return]


def test_the_outbound_chosen_lists_the_return_and_shows_its_segment() -> None:
    call = LeanCall()
    outs, _ = _found(call)
    picked = call.choose(outbound_id=outs[-1])
    answer = data(picked)
    assert answer["status"] == "ok" and answer["trip"] == "round trip"
    assert answer["outbound"]["id"] == outs[-1] and answer["outbound"]["departs"] == "21:00"
    assert answer["outbound"]["day"] == {"date": OUT, "weekday": "Thursday"}
    assert answer["missing"] == ["return"] and "total" not in answer
    assert answer["listed"]["return"]["count"] == 4 and "outbound" not in answer["listed"]
    card = picked.card
    assert card is not None and card.slot == "return" and card_passes(picked)
    assert [r.mark for r in card.rows].count("chosen") == 1  # the outbound pick, kept beside
    assert call.draft.chosen_outbound is not None and call.draft.chosen_outbound.flight == 107


def test_both_legs_chosen_give_the_total_and_the_review() -> None:
    call = LeanCall()
    outs, backs = _found(call)
    picked = call.choose(outbound_id=outs[0], return_id=backs[2])
    answer = data(picked)
    fares = answer["outbound"]["fare"] + answer["return"]["fare"]
    assert answer["missing"] == [] and answer["total"] == fares == call.total()
    assert answer["travelers"] == 1 and answer["cabin"] == "economy"
    assert picked.card is not None and picked.card.slot == "review"
    assert picked.card.title.startswith(TRIP_EN) and card_passes(picked)


def test_a_chosen_leg_keeps_its_length_and_nonstop_for_the_booking_too() -> None:
    call = LeanCall()
    out = data(call.find(destination="Jeddah", depart=OUT, return_date=BACK))["outbound"]
    out = out["options"][0]
    back = data(call.choose(outbound_id=out["id"]))["listed"]["return"]["options"][1]
    answer = data(call.choose(return_id=back["id"]))
    booked: dict[str, Any] = dict(chosen_legs(call.airline, call.draft, "en"))  # book_trip's
    for leg, option in (("outbound", out), ("return", back)):
        assert answer[leg]["duration"] == option["duration"] == booked[leg]["duration"]
        assert answer[leg]["nonstop"] is True and answer[leg]["arrives"] == option["arrives"]


def test_a_saudi_reply_gets_the_trip_kind_in_saudi_and_in_msa() -> None:
    # As the route: f-dev-lean-3 read «رايح جاي» back to an MSA caller, given no MSA form.
    answer = data(chosen_trip("ar-SA").choose())
    assert answer["trip"] == "رايح جاي" and answer["trip_msa"] == "ذهاب وعودة"
    assert "trip_msa" not in data(chosen_trip().choose())  # an English reply's has none


def test_more_travelers_price_the_trip_again() -> None:
    call = chosen_trip()
    one = call.total()
    answer = data(call.choose(travelers=2))
    assert answer["travelers"] == 2 and answer["total"] == 2 * one


def test_a_cabin_that_leaves_no_seats_loses_the_legs_and_lists_them_again() -> None:
    call = chosen_trip()
    answer = data(call.choose(cabin="business", travelers=9))
    assert answer["missing"] == ["outbound", "return"] and "total" not in answer
    assert answer["lost"] == [
        {"leg": "outbound", "departs": "06:00"},
        {"leg": "return", "departs": "07:45"},
    ]
    assert set(answer["listed"]) == {"outbound"}  # one leg at a time: the return after it
    assert all(not o["seats_ok"] for o in answer["listed"]["outbound"]["options"])
    assert (call.draft.cabin, call.draft.travelers) == ("business", 9)


def test_a_change_before_any_pick_lists_the_outbound_alone() -> None:
    # As find_flights gives it: both days listed again brought back the two-day listing.
    call = LeanCall()
    _found(call)
    answer = data(call.choose(travelers=2))
    assert answer["missing"] == ["outbound", "return"] and set(answer["listed"]) == {"outbound"}


def test_the_way_back_is_listed_before_the_way_out_when_asked() -> None:
    # A caller may ask about the way back first; leg by leg stays the default.
    call = LeanCall()
    _, backs = _found(call)
    answer = data(call.choose(list_leg="return"))
    assert answer["missing"] == ["outbound", "return"] and set(answer["listed"]) == {"return"}
    assert [o["id"] for o in answer["listed"]["return"]["options"]] == backs
    assert call.draft.chosen_outbound is None and call.draft.chosen_return is None
    picked = data(call.choose(return_id=backs[1]))  # then picked first, too
    assert picked["missing"] == ["outbound"] and set(picked["listed"]) == {"outbound"}
    assert "list_leg" in DESCRIPTION


def test_a_full_flight_of_the_leg_listed_is_noted() -> None:
    # Run F's f08: the return day from Doha has T2 254 with no seat, listed after the pick.
    call = LeanCall()
    found = call.find(destination="Doha", depart=OUT, return_date=BACK)
    assert "note" not in data(found)  # the outbound's flights all have seats
    answer = data(call.choose(outbound_id=ids(found)[0]))
    full = [o["id"] for o in answer["listed"]["return"]["options"] if not o["seats_ok"]]
    assert full == ["T2-254-2026-11-21"] and "seats_ok false" in answer["note"]
    assert "note" not in data(chosen_trip().choose())  # nothing listed, no note


def test_choosing_says_it_books_nothing() -> None:
    # f-dev-lean-4, f01 and f30: a trip chosen with its total read as booked («حجزت لك»).
    assert "It books nothing: book_trip books." in DESCRIPTION


def test_an_id_not_listed_is_refused_with_the_others_and_writes_nothing() -> None:
    call = LeanCall()
    outs, _ = _found(call)
    before = call.draft
    answer = data(call.choose(outbound_id="T2-999-2026-11-19", cabin="business"))
    assert answer["status"] == "unknown_id" and answer["leg"] == "outbound"
    assert [o["id"] for o in answer["others"]] == outs
    assert set(answer["others"][0]) == {"id", "fare", "seats_ok"}
    assert call.draft == before


def test_a_flight_with_no_seats_for_the_travelers_is_refused() -> None:
    call = LeanCall()
    outs, _ = _found(call)
    answer = data(call.choose(outbound_id=outs[0], cabin="business", travelers=9))
    assert answer["status"] == "no_seats" and answer["id"] == outs[0]
    assert outs[0] not in [o["id"] for o in answer["others"]]
    assert call.draft.chosen_outbound is None and call.draft.cabin == "economy"


def test_nothing_listed_and_a_cabin_not_sold_are_refused() -> None:
    call = LeanCall()
    answer = data(call.choose(outbound_id="T2-101-2026-11-19"))
    assert answer == {"status": "nothing_listed", "note": NOTHING_LISTED}
    _found(call)
    answer = data(call.choose(cabin="first"))
    assert answer["status"] == "cabin_not_offered" and answer["offered"] == ["economy", "business"]


def test_a_return_id_on_a_one_way_trip_is_not_listed() -> None:
    call = LeanCall()
    call.find(destination="Jeddah", depart=OUT)
    answer = data(call.choose(return_id="T2-102-2026-11-21"))
    assert answer["status"] == "unknown_id" and answer["others"] == []
