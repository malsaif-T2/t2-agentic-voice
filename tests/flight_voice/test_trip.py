"""The trip a call plans, kept in code: one draft per call, at most 64 calls, dropped when the
call ends; a search, a cabin or traveler change and one way each make a new draft, a leg short
of seats losing its choice; and a tool cancelled before its one assignment leaves the draft as
it was."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from flight_voice.airline.bookings import Leg
from flight_voice.airline.fares import seats_left
from flight_voice.airline.schedule import find_flight
from flight_voice.trip import MAX_CALLS, Shown, TripBook, TripDraft, changed
from pydantic import ValidationError
from t2_agentic_voice.events import CallEnded, CallReport

TODAY = date(2026, 11, 16)
OUT = Leg(flight=401, day=date(2026, 12, 17))
BACK = Leg(flight=404, day=date(2026, 12, 20))
NOW = datetime(2026, 11, 16, 9, tzinfo=UTC)


def _london() -> TripDraft:
    return TripDraft().searched(
        origin="RUH",
        destination="LHR",
        depart=OUT.day,
        return_date=BACK.day,
        one_way=False,
        travelers=1,
        cabin="economy",
    )


def _complete() -> TripDraft:
    return _london().choose("outbound", OUT).choose("return", BACK)


def _ended(call_id: str) -> CallEnded:
    report = CallReport(
        call_id=call_id, agent="flight", started_at=NOW, ended_at=NOW, ended_by="hangup"
    )
    return CallEnded(call_id=call_id, at=NOW, report=report)


def test_a_new_draft_holds_the_travelers_defaults_and_lacks_everything_else() -> None:
    draft = TripDraft()
    assert (draft.origin, draft.one_way, draft.travelers, draft.cabin) == (
        "RUH",
        False,
        1,
        "economy",
    )
    assert draft.missing() == ("destination", "depart", "return_date", "outbound", "return")
    assert draft.legs() == () and draft.total(TODAY) is None


def test_a_draft_is_frozen_and_bounded() -> None:
    with pytest.raises(ValidationError):
        TripDraft(travelers=10)
    with pytest.raises(ValidationError):
        _complete().travelers = 2  # type: ignore[misc]


def test_a_complete_trip_has_its_legs_and_total() -> None:
    draft = _complete()
    assert draft.missing() == () and draft.legs() == (OUT, BACK)
    assert draft.total(TODAY) == 3560 + 2960
    assert draft.total(date(2026, 12, 18)) is None  # its outbound has left: no price
    one = changed(draft, one_way=True).draft
    assert one.legs() == (OUT,) and one.return_date is None and one.total(TODAY) == 3560


def test_the_options_listed_are_kept_in_the_order_said() -> None:
    options = (Shown(n=1, flight=401, day=OUT.day), Shown(n=2, flight=403, day=OUT.day))
    draft = _london().listed("outbound", options)
    assert draft.shown("outbound") == options and draft.shown("return") == ()
    assert draft.chosen("outbound") is None


def test_a_search_keeps_a_legs_choice_only_on_the_same_route_and_day() -> None:
    draft = _complete()
    same = draft.searched(
        origin="RUH",
        destination="LHR",
        depart=OUT.day,
        return_date=date(2026, 12, 21),
        one_way=False,
        travelers=1,
        cabin="economy",
    )
    assert same.chosen_outbound == OUT and same.chosen_return is None
    paris = draft.searched(
        origin="RUH",
        destination="CDG",
        depart=OUT.day,
        return_date=BACK.day,
        one_way=False,
        travelers=1,
        cabin="economy",
    )
    assert paris.legs() == () and paris.shown_outbound == ()


def test_a_cabin_change_keeps_a_leg_with_seats_and_drops_one_without() -> None:
    """T2 401 on 17 December has 2 first-class seats; T2 404 on 20 December has none."""
    out = find_flight(401)
    back = find_flight(404)
    assert out is not None and back is not None
    assert seats_left(out, OUT.day, "first") == 2
    assert seats_left(back, BACK.day, "first") == 0
    change = changed(_complete(), cabin="first")
    assert change.lost == ("return",)
    assert change.draft.cabin == "first" and change.draft.chosen_outbound == OUT
    assert change.draft.chosen_return is None and change.draft.missing() == ("return",)


def test_a_traveler_count_past_the_seats_drops_the_leg() -> None:
    change = changed(_complete(), cabin="business", travelers=8)
    assert change.lost == ("outbound", "return") and change.draft.legs() == ()
    two = changed(_complete(), travelers=2)
    assert two.lost == () and two.draft.total(TODAY) == 2 * (3560 + 2960)
    with pytest.raises(ValidationError):
        changed(_complete(), travelers=10)


def test_the_book_keeps_one_draft_per_call() -> None:
    book = TripBook()
    assert book.get("c-1") == TripDraft() and len(book) == 0
    book.put("c-1", _complete())
    book.put("c-2", _london())
    assert book.get("c-1") == _complete() and book.get("c-2") == _london()
    started = TripBook(start=lambda: TripDraft(cabin="business"))
    assert started.get("c-9").cabin == "business"


def test_the_book_drops_the_oldest_call_past_its_cap() -> None:
    book = TripBook()
    for n in range(MAX_CALLS):
        book.put(f"c-{n}", _london())
    book.put("c-0", _complete())  # c-0 is now the newest
    book.put("c-new", _london())
    assert len(book) == MAX_CALLS == 64
    assert book.get("c-1") == TripDraft()  # the oldest, dropped
    assert book.get("c-0") == _complete() and book.get("c-new") == _london()


def test_the_book_drops_a_call_when_it_ends() -> None:
    book = TripBook()
    book.put("c-1", _complete())
    book.put("c-2", _complete())
    asyncio.run(book.call_ended(_ended("c-1")))
    assert book.get("c-1") == TripDraft() and book.get("c-2") == _complete()
    book.drop("c-unknown")
    assert len(book) == 1


def test_a_tool_cancelled_before_it_puts_leaves_the_draft_whole() -> None:
    """A tool reads the draft, awaits the airline, then puts its new draft in one assignment:
    cancelled while it awaits, the book holds the draft as it was."""
    book = TripBook()
    book.put("c-1", _london())
    waiting = asyncio.Event()

    async def tool() -> None:
        draft = book.get("c-1").choose("outbound", OUT)
        waiting.set()
        await asyncio.sleep(10)
        book.put("c-1", draft.choose("return", BACK))

    async def scene() -> None:
        task = asyncio.create_task(tool())
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scene())
    assert book.get("c-1") == _london()
