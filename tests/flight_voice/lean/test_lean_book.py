"""The lean agent's `book_trip` (flight_voice/lean/book.py): it books the trip chosen so far
only once the booking check holds, for the verified traveler alone, and returns the reference,
the total, the route and the review card marked booked; and, writing nothing, it answers a trip
not complete, a trip not confirmed (its one fixed `say`), a booking already made (told as it was
booked, though the trip changed since), a refusal of
the store, and a write that did not answer (looked up by its request ID when the store can
find one, `unknown` when it cannot, and never written again in that call)."""

from __future__ import annotations

import pytest
from flight_voice.lean import book
from flight_voice.lean.book import NOT_CONFIRMED
from flight_voice.tools.cards import TRIP_EN

from tests.flight_voice.lean.lean_support import OUT, LeanCall, chosen_trip, ids
from tests.flight_voice.tools.tool_support import CALLER, airline, card_passes, data

STRANGER = CALLER.model_copy(update={"attributes": {"traveler_id": "T-9999"}})


def _agreed(call: LeanCall) -> LeanCall:
    call.said(f"Riyadh to Jeddah and back, economy, one traveler, {call.total()} riyals in all.")
    call.heard("yes")
    return call


def test_an_agreed_trip_is_booked_once_with_its_reference_and_card() -> None:
    call = _agreed(chosen_trip())
    total = call.total()
    made = call.book()
    answer = data(made)
    assert answer["status"] == "booked" and answer["total"] == total
    assert answer["route"] == "Riyadh to Jeddah" and answer["trip"] == "round trip"
    (booking,) = call.airline.bookings.made
    assert answer["reference"] == booking.reference and booking.traveler_id == "T-0001"
    assert [leg.flight for leg in booking.legs] == [101, 102] and booking.total_sar == total
    card = made.card
    assert card is not None and card.slot == "review" and card.title.startswith(TRIP_EN)
    assert card.rows[-1].title == f"Booked · Reference {booking.reference}" and card_passes(made)
    again = data(call.book())
    assert again["status"] == "already_booked" and again["reference"] == booking.reference
    assert len(call.airline.bookings.writes) == 1


def test_a_trip_changed_after_the_booking_is_answered_with_the_trip_booked() -> None:
    call = _agreed(chosen_trip())
    made = call.book()
    booked = data(made)
    listed = call.find(destination="Jeddah", depart=OUT, return_date="2026-11-21")
    call.choose(outbound_id=ids(listed)[2])  # another outbound, chosen after the booking
    assert call.draft.chosen_outbound is not None and call.draft.chosen_outbound.flight != 101
    again = call.book()
    answer = data(again)
    assert answer["status"] == "already_booked" and answer["reference"] == booked["reference"]
    assert answer["outbound"] == booked["outbound"] and answer["outbound"]["id"] == f"T2-101-{OUT}"
    assert again.card is not None and made.card is not None
    assert again.card.rows == made.card.rows  # the booked trip's times, never the new pick's
    assert len(call.airline.bookings.writes) == 1


def test_an_arabic_booking_card_says_booked_in_arabic() -> None:
    call = _agreed(chosen_trip("ar-SA"))
    made = call.book()
    assert made.card is not None and made.card.rows[-1].title.startswith("تم الحجز · رقم الحجز")


def test_a_trip_not_confirmed_books_nothing() -> None:
    call = chosen_trip()
    assert data(call.book()) == NOT_CONFIRMED
    call.said("Shall I book the trip for you?")
    call.heard("yes")
    assert data(call.book()) == NOT_CONFIRMED
    assert call.airline.bookings.writes == []


def test_a_trip_not_complete_books_nothing() -> None:
    call = LeanCall()
    listed = call.find(destination="Jeddah", depart=OUT, return_date="2026-11-21")
    call.choose(outbound_id=ids(listed)[0])
    assert data(call.book()) == {"status": "incomplete", "missing": ["return"]}
    assert data(LeanCall().book()) == {"status": "incomplete", "missing": ["outbound", "return"]}


def test_a_caller_the_airline_does_not_know_is_refused() -> None:
    call = _agreed(chosen_trip())
    refused = call.book(caller=STRANGER)
    assert not refused.ok and call.airline.bookings.writes == []


def test_a_refusal_of_the_store_books_nothing_and_may_be_tried_again() -> None:
    call = LeanCall(flights=airline())
    call.airline.bookings.mode = "refuse"
    _agreed(chosen_trip_on(call))
    assert data(call.book()) == {"status": "refused", "reason": "refused"}
    call.airline.bookings.mode = "answer"
    assert data(call.book())["status"] == "booked"


def test_a_late_write_is_looked_up_and_a_lost_one_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(book, "WRITE_S", 0.05)
    late = _agreed(chosen_trip())
    late.airline.bookings.mode, late.airline.bookings.late_s = "late", 0.5
    assert data(late.book())["status"] == "booked"
    lost = _agreed(chosen_trip())
    lost.airline.bookings.mode, lost.airline.bookings.late_s = "timeout", 0.5
    assert data(lost.book()) == {"status": "unknown"}
    lost.airline.bookings.mode = "answer"
    assert data(lost.book()) == {"status": "unknown"}  # never a second write beside it
    assert len(lost.airline.bookings.writes) == 1 and lost.airline.bookings.made == ()


def chosen_trip_on(call: LeanCall) -> LeanCall:
    """`call` with the Jeddah trip found and the first flight each way chosen."""
    listed = call.find(destination="Jeddah", depart=OUT, return_date="2026-11-21")
    call.choose(outbound_id=ids(listed)[0], return_id=ids(listed, "return")[0])
    return call
