"""The lean agent's booking check (flight_voice/lean/booking_check.py), fed the call's events as
the runtime's observers would: it holds once a reply ended since the trip was completed and the
caller spoke after it, its total said or not (the owner's ruling of 2026-11-18; a later turn that
cut the reply counting though its transcript came before the reply's end); and it refuses with no
caller turn after the reply, and the trip changed after the reply. A yes said over the closing
question, which the library answers only once the reply has ended (D-116), so its transcript came
first, holds when what had played as its speech began (`UserTurnEnded.reply_played`) begins the
reply; never when nothing had played, over another reply, or is the turn the reply answers. A
total is read in
digits (a thousands mark, a space before three digits among them, Arabic-Indic digits) or in
words in English, Saudi Arabic and MSA; a call held in text reads its events from the call
itself, and an ended call's are dropped."""

from __future__ import annotations

from datetime import UTC, datetime

from flight_voice.lean.booking_check import BookingCheck, stated_at
from t2_agentic_voice.events import AgentSpeechEnded, Event, UserTurnEnded
from t2_agentic_voice.languages import speak_number

from tests.flight_voice.lean.lean_support import LeanCall, chosen_trip, ids
from tests.flight_voice.tools.tool_support import CALL_ID


def _summary(call: LeanCall) -> str:
    return f"Riyadh to Jeddah and back, economy, one traveler: {call.total()} riyals in all."


def _holds(call: LeanCall) -> bool:
    return call.check.confirmed(CALL_ID, call.draft, call.total())


def test_the_check_holds_once_the_total_played_and_the_caller_spoke() -> None:
    call = chosen_trip()
    call.said(_summary(call) + " Shall I book it?")
    assert not _holds(call)  # the caller has not spoken since
    call.heard("yes")
    assert _holds(call)


def test_a_yes_books_with_no_total_said() -> None:
    # The owner, 2026-11-18: "the confirmation can be done before the agent saying the total".
    call = chosen_trip()
    call.said("Riyadh to Jeddah and back, economy, one traveler. Shall I book it?")
    assert not _holds(call)
    call.heard("yes")
    assert _holds(call)


def test_a_yes_after_a_reply_cut_before_its_total_books() -> None:
    call = chosen_trip()
    call.said(_summary(call), played=0.5)
    call.heard("yes")
    assert _holds(call)


def test_a_turn_that_cut_the_reply_after_its_total_holds_though_it_ended_first() -> None:
    call = chosen_trip()
    call.heard("the first ones")  # turn 1: the summary answers it
    summary = _summary(call) + " Shall I book it?"
    call.heard("yes, book it")  # turn 2, over the question: its transcript came first
    call.said(summary, played=0.93, turn=1)  # then the overlap's verdict cut the summary
    assert _holds(call)


def test_a_turn_before_the_reply_ended_counts_only_once_its_total_played() -> None:
    whole = chosen_trip()
    whole.heard("the first ones")
    whole.heard("mm", played="")  # turn 2, over the summary, which went on and played whole
    whole.said(_summary(whole) + " Shall I book it?", played=1.0, turn=1)
    assert not _holds(whole)
    early = chosen_trip()
    early.heard("the first ones")
    early.heard("yes")  # turn 2 cut the summary before its total played: it holds now
    early.said(_summary(early) + " Shall I book it?", played=0.3, turn=1)
    assert _holds(early)
    same = chosen_trip()
    same.heard("the first ones")  # turn 1 itself, heard before the cut reply that answers it
    same.said(_summary(same) + " Shall I book it?", played=0.93, turn=1)
    assert not _holds(same)


def test_a_yes_over_the_closing_question_holds_once_the_total_had_played() -> None:
    call = chosen_trip()
    call.heard("the first ones")  # turn 1: the summary answers it
    summary = _summary(call)
    call.heard("yes", played=summary)  # turn 2, over the question: its transcript came first
    call.said(f"{summary} Shall I book it?", played=1.0, turn=1)  # the reply went on, whole
    assert _holds(call)


def test_a_yes_over_the_reply_before_its_total_played_is_refused() -> None:
    early = chosen_trip()
    early.heard("the first ones")
    early.heard("yes", played="Riyadh to Jeddah and back.")  # before the total: it holds now
    early.said(f"Riyadh to Jeddah and back. {_summary(early)} Shall I book it?", turn=1)
    assert _holds(early)
    for case in ("nothing played", "another reply", "silent"):
        call = chosen_trip()
        call.heard("the first ones")
        opening = "Riyadh to Jeddah and back."
        played = {
            "nothing played": "",
            "another reply": f"Said before: {call.total()} riyals.",
            "silent": None,
        }[case]
        call.heard("yes", played=played)
        call.said(f"{opening} {_summary(call)} Shall I book it?", turn=1)
        assert not _holds(call), case
    same = chosen_trip()
    same.heard("the first ones", played=_summary(same))  # the turn the reply answers itself
    same.said(f"{_summary(same)} Shall I book it?", turn=1)
    assert not _holds(same)


def test_no_caller_turn_after_the_reply_is_refused() -> None:
    call = chosen_trip()
    call.heard("the first ones")
    call.said(_summary(call))
    assert not _holds(call)


def test_a_trip_changed_after_the_summary_is_refused() -> None:
    call = chosen_trip()
    call.said(_summary(call))
    call.heard("make it two of us")
    call.choose(travelers=2)
    assert not _holds(call)
    call.said(_summary(call))  # the new total said
    call.heard("yes")
    assert _holds(call)


def test_a_summary_said_before_the_trip_was_complete_never_counts() -> None:
    call = LeanCall()
    found = call.find(destination="Jeddah", depart="2026-11-19")
    call.said("Riyadh to Jeddah on Thursday.")
    call.heard("the first one")
    call.choose(outbound_id=ids(found)[0])
    assert not _holds(call)


def test_a_total_is_read_in_digits_and_in_words() -> None:
    for text in ("Total 4230 riyals.", "Total 4,230 riyals.", "المجموع ٤٬٢٣٠ ريال."):
        assert stated_at(text, 4230) is not None, text
    for words in (
        speak_number(4230, language="en"),
        speak_number(4230, language="ar-SA", register="saudi"),
        speak_number(4230, language="ar-SA", register="msa"),
    ):
        assert stated_at(f"The total is {words} riyals.", 4230) is not None, words
    assert stated_at("Total 14230 riyals.", 4230) is None
    assert stated_at("Total 42300 riyals.", 4230) is None
    # f-dev-lean-4, f09: "total 3 080. Shall I book it?" never found, so the yes booked nothing;
    # a space before three digits is a thousands mark, as the comma is, and only there.
    for space in (" ", chr(0x00A0), chr(0x2009), chr(0x202F)):
        assert stated_at(f"total 3{space}080. Shall I book it?", 3080) is not None, hex(ord(space))
    assert stated_at("Total 13 080 riyals.", 3080) is None
    assert stated_at("Total 3 0800 riyals.", 3080) is None
    at = stated_at("Total 880. Shall I book it now, or change something first?", 880)
    assert at is not None and 0 < at < 0.3


def test_a_call_in_text_reads_its_events_from_the_call() -> None:
    call = chosen_trip()
    events: list[Event] = []
    call.check.read_from(lambda: events)
    at = datetime(2026, 11, 16, 9, tzinfo=UTC)
    events.append(
        AgentSpeechEnded(call_id=CALL_ID, turn_id=0, at=at, text=_summary(call), played_fraction=1)
    )
    events.append(UserTurnEnded(call_id="another", turn_id=1, at=at, heard="yes"))
    assert not _holds(call)  # another call's turn is not this caller's
    events.append(UserTurnEnded(call_id=CALL_ID, turn_id=1, at=at, heard="yes"))
    assert _holds(call)


def test_an_ended_call_is_dropped_and_the_calls_kept_are_capped() -> None:
    call = chosen_trip()
    call.said(_summary(call))
    call.heard("yes")
    assert len(call.check) == 1
    call.ended()
    assert len(call.check) == 0
    capped = BookingCheck(max_calls=2)
    for n in range(3):
        capped.ledger(f"call-{n}")
    assert len(capped) == 2
