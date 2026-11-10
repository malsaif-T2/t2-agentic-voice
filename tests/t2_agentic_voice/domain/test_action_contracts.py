"""What plan 007's Block 0 settled for its tracks holds: the yes rule's inputs bind the draft that
was read back, the outbox's row is frozen and hides what was said, the states are the design's,
a read-back carries the line that ends it with no yes and the line said while the write runs,
and a declined action says how. Its
stubs' own tests are in the files named test_stubs_track_*.py, each its track's to delete as it
fills them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from t2_agentic_voice.agent.events import ClauseBlocked, ReadBackRequested
from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind, TalkerTurn
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords
from t2_agentic_voice.domain.action_flow import ACTION_STATES, ENDS
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.claims import ActionEvidence, ClaimVerdict
from t2_agentic_voice.domain.ports.outbox import OutboxEntry
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    Correction,
    Declined,
    Yes,
    YesOutcome,
    _issued,
    is_confirmed,
)
from t2_agentic_voice.voice.session.read_back import played_receipt

AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
RECEIPT = played_receipt(
    action="open_request",
    draft_json='{"summary": "made up"}',
    reply_id=4,
    summary_played_at=6.0,
    question_ended_at=None,
)


def _heard(text: str = "yes send it") -> HeardWords:
    values = {"turn_id": 9, "text": text, "language": "en", "at": 9.0, "speech_at": 8.0}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def test_a_confirmed_action_takes_its_draft_from_the_receipt() -> None:
    confirmed = _issued(_heard(), RECEIPT, speech_at=8.0)
    assert is_confirmed(confirmed) is True
    assert (confirmed.action, confirmed.draft_json, confirmed.reply_id) == (
        RECEIPT.action,
        RECEIPT.draft_json,
        RECEIPT.reply_id,
    )
    assert (confirmed.turn_id, confirmed.words) == (9, "yes send it")
    assert "made up" not in repr(confirmed) and "yes send it" not in repr(confirmed)
    assert "made up" not in repr(RECEIPT)


def test_the_yes_rule_answers_one_of_four_ways() -> None:
    confirmed = _issued(_heard(), RECEIPT, speech_at=8.0)
    outcomes: list[YesOutcome] = [
        Yes(confirmed=confirmed),
        Declined(words="no"),
        Correction(words="change it"),
        AskAgain(),
    ]
    assert {type(each).__name__ for each in outcomes} == {
        "Yes",
        "Declined",
        "Correction",
        "AskAgain",
    }


def _an_entry() -> OutboxEntry:
    return OutboxEntry(
        request_id="r-1",
        call_id="c-1",
        subject="made-up",
        action="open_request",
        draft_json='{"summary": "made up"}',
        created_at=AT,
        updated_at=AT,
    )


def test_an_outbox_row_is_frozen_refuses_a_misspelt_key_and_hides_what_was_said() -> None:
    entry = _an_entry()
    assert entry.state == "sending" and entry.result_json is None
    assert "made up" not in repr(entry)
    with pytest.raises(ValidationError):
        entry.state = "done"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        OutboxEntry.model_validate({**entry.model_dump(), "extra": "x"})
    with pytest.raises(ValidationError):
        OutboxEntry.model_validate({**entry.model_dump(), "state": "gone"})


def test_the_flows_states_end_where_the_design_says() -> None:
    assert ACTION_STATES == (
        "confirming",
        "confirmed",
        "sending",
        "done",
        "failed",
        "unknown",
        "declined",
    )
    assert {"done", "failed", "unknown", "declined"} == ENDS


LINE = SpokenLine(text="number 123", spoken="number one two three")
DECLINED = SpokenLine(text="I have not opened it.", spoken="I have not opened it.")
SENDING = SpokenLine(text="One moment, opening it.", spoken="One moment, opening it.")


def _plan(**changes: Any) -> ReadBackPlan:
    values: dict[str, Any] = {
        "action": "open_request",
        "tool_call_id": "t-1",
        "draft_json": '{"summary": "made up"}',
        "summary": LINE,
        "question": LINE,
        "asked_again": LINE,
        "declined": DECLINED,
        "sending": SENDING,
        "language": "en",
        "max_attempts": 2,
    }
    return ReadBackPlan.model_validate({**values, **changes})


def test_a_read_back_reaches_the_session_as_an_event_and_a_summary_apart() -> None:
    event = ReadBackRequested(plan=_plan())
    assert event.plan.summary is LINE
    assert ClauseBlocked(text="x", language="en").reason == "unsupported_id"
    blocked = ClauseBlocked(text="x", language="en", reason="unsupported_claim")
    assert blocked.reason == "unsupported_claim"


def test_a_read_back_carries_its_sending_line_for_the_session_to_speak() -> None:
    """The session speaks the action's `sending` line, or the library's, once the yes rule
    issues the `ConfirmedAction`, before the job's outcome (the owner's ruling, plan 007):
    `voice` cannot render a template, so the read-back carries it rendered."""
    assert _plan().sending is SENDING
    values = _plan().model_dump()
    del values["sending"]
    with pytest.raises(ValidationError):
        ReadBackPlan.model_validate(values)


def test_a_read_back_carries_its_declined_line_for_the_session_to_speak() -> None:
    """The session speaks the action's own `declined` line only where no talker turn can answer:
    nothing usable heard after the last ask-again, so no `TalkerTurn` can be built, and `voice`
    cannot render a template itself. After a plain no the talker answers."""
    assert _plan().declined is DECLINED
    values = _plan().model_dump()
    del values["declined"]
    with pytest.raises(ValidationError):
        ReadBackPlan.model_validate(values)
    with pytest.raises(ValidationError):
        TalkerTurn(turn_id=3, words="")


@pytest.mark.parametrize(
    ("kind", "words"), [("no", "nope, leave it"), ("correction", "make it urgent")]
)
def test_a_declined_action_tells_the_talker_a_no_from_a_correction(
    kind: DeclineKind, words: str
) -> None:
    declined = DeclinedAction(action="open_request", kind=kind, words=words)
    turn = TalkerTurn(turn_id=3, words=words, declined=declined)
    assert turn.declined is not None and turn.declined.kind == kind
    assert words not in repr(declined)


def test_a_declined_action_names_one_of_four_kinds() -> None:
    assert get_args(DeclineKind) == ("no", "correction", "stopped", "unclear")
    unclear = DeclinedAction(action="open_request", kind="unclear", words="")
    assert unclear.kind == "unclear"  # asked max_attempts times, and nothing heard
    with pytest.raises(ValidationError):
        DeclinedAction.model_validate({"action": "open_request", "words": "no"})
    with pytest.raises(ValidationError):
        DeclinedAction.model_validate({"action": "open_request", "kind": "maybe", "words": ""})


def test_claim_evidence_is_plain_data() -> None:
    evidence = ActionEvidence(action="open_request", texts=("1234",))
    verdict = ClaimVerdict(claimed=("open_request",), passed=True)
    assert evidence.texts == ("1234",) and verdict.passed and verdict.unsupported == ()
