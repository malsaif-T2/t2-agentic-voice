"""The action runner's `run`, the `ActionJobs` port (actions/action_runner.py, action_job.py,
action_writes.py; the design's 6.4; docs/SECURITY.md, invariants 1, 2 and 6): only a confirmed
action the yes rule issued is carried out; its outbox row is written `sending` before the
write; each error has its meaning, a backend that refuses, raises, times out, loses its reply or
replies late, each with and without a lookup; the same confirmed action never goes twice; a
stop never cuts a write in half; only a write that really returned, or that a lookup found, is
recorded, in its own call's record or in the one record the runner was given; and nothing
shown holds a draft's value or a reason."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from t2_agentic_voice.actions import spoken_lines
from t2_agentic_voice.actions.action_runner import NOT_CONFIRMED, ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.core.events import ActionCompleted, ActionUnconfirmed
from t2_agentic_voice.domain.action_lines import ActionLines
from t2_agentic_voice.domain.completed_action import is_recorded
from t2_agentic_voice.domain.ports.outbox import OutboxEntry

from tests.leaks import holding, shown
from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CALLER,
    CONVERSATION,
    ISSUED,
    REASON,
    SUMMARY,
    Mode,
    Rig,
    confirmed_of,
    until,
)

LIBRARY = ActionLines(
    sending="Library sending.",
    failed="Library failed.",
    unknown="Library unknown.",
    declined="Library declined.",
    asked_again="Library asked again.",
)


async def _row(rig: Rig, request_id: str) -> OutboxEntry:
    row = await rig.outbox.get(request_id)
    assert row is not None
    return row


def test_a_write_has_its_outbox_row_before_it_is_sent_and_is_recorded_once_done() -> None:
    rig = Rig()

    async def scenario() -> tuple[Any, OutboxEntry]:
        outcome = await rig.confirmed_run()
        return outcome, await _row(rig, outcome.request_id)

    outcome, row = asyncio.run(scenario())
    [before] = rig.backend.rows_at_write
    assert before is not None and before.state == "sending"
    assert (before.request_id, before.call_id, before.subject) == (
        outcome.request_id,
        CALL_ID,
        CALLER.subject,
    )
    assert (outcome.action, outcome.kind) == ("open_request", "done")
    assert outcome.line.text == f"Done, your number is {ISSUED}."
    assert outcome.line.spoken == (
        "Done, your number is two zero two six, one one one zero, eight two zero zero, "
        "zero one two three."
    )
    assert row.state == "done" and row.result_json is not None and ISSUED in row.result_json
    [entry] = rig.runner.record(CALL_ID).entries()
    assert is_recorded(entry) and entry.request_id == outcome.request_id
    assert ISSUED in entry.evidence and entry.action == "open_request"
    assert rig.events == [
        ActionCompleted(
            call_id=CALL_ID,
            turn_id=9,
            at=rig.clock.wall(),
            action="open_request",
            request_id=outcome.request_id,
            result=entry.result_json,
        )
    ]
    assert outcome.result_json == entry.result_json and ISSUED in outcome.result_json


def test_the_write_is_told_its_request_id_the_heard_consent_and_the_conversation() -> None:
    rig = Rig()
    outcome = asyncio.run(rig.confirmed_run())
    [(ctx, draft)] = rig.backend.writes
    assert ctx.request_id == outcome.request_id and ctx.caller == CALLER
    assert (ctx.consent.words, ctx.consent.source, ctx.consent.speech_at) == (
        "yes, send it",
        "speech_to_text",
        8.0,
    )
    assert ctx.conversation == CONVERSATION and ctx.record == ()
    assert draft.summary == SUMMARY and draft.category == "software"


def test_the_outcome_is_said_in_the_calls_language() -> None:
    rig = Rig()

    async def scenario() -> Any:
        return await rig.run(confirmed_of(await rig.plan("ar-SA")), language="ar-SA")

    outcome = asyncio.run(scenario())
    assert outcome.line.text == f"تم، رقم الطلب {ISSUED}."
    assert outcome.line.spoken.startswith("تم، رقم الطلب اثنان صفر اثنان ستة، واحد")


@pytest.mark.parametrize(("mode", "state"), [("reject", "rejected"), ("not_sent", "not_sent")])
def test_a_write_definitely_not_done_is_failed_never_looked_up_and_never_recorded(
    mode: Mode, state: str
) -> None:
    rig = Rig(mode)

    async def scenario() -> tuple[Any, OutboxEntry]:
        outcome = await rig.confirmed_run()
        return outcome, await _row(rig, outcome.request_id)

    outcome, row = asyncio.run(scenario())
    assert outcome.kind == "failed"
    assert outcome.line.text == "I could not open the software request."
    assert (row.state, row.note) == (state, state)
    assert rig.backend.lookups == [] and len(rig.backend.writes) == 1
    assert rig.runner.record(CALL_ID).entries() == ()
    [event] = rig.events
    assert isinstance(event, ActionUnconfirmed) and event.kind == "failed"


@pytest.mark.parametrize(
    ("mode", "lookup", "advance_s", "kind", "state", "note"),
    [
        ("lost_reply", True, 20.0, "done", "done", "looked_up"),
        ("lost_reply", False, 20.0, "unknown", "flagged", "timed_out, no_lookup"),
        ("hang", True, 20.0, "unknown", "flagged", "timed_out, not_found"),
        ("raise", True, 0.0, "unknown", "flagged", "raised, not_found"),
        ("raise", False, 0.0, "unknown", "flagged", "raised, no_lookup"),
        ("odd", True, 0.0, "unknown", "flagged", "unreadable_result, not_found"),
    ],
    ids=[
        "lost reply, found",
        "lost reply, no lookup",
        "timeout, not found",
        "raised, not found",
        "raised, no lookup",
        "unreadable, not found",
    ],
)
def test_a_write_with_no_reply_is_looked_up_by_its_request_id_and_never_sent_again(
    mode: Mode, lookup: bool, advance_s: float, kind: str, state: str, note: str
) -> None:
    """Invariant 6: a timeout or an unknown failure is looked up when the action has a lookup;
    found, it is done and recorded; otherwise unknown, with no number, the row flagged."""
    rig = Rig(mode, lookup=lookup)

    async def scenario() -> tuple[Any, OutboxEntry]:
        outcome = await rig.confirmed_run(advance_s=advance_s)
        return outcome, await _row(rig, outcome.request_id)

    outcome, row = asyncio.run(scenario())
    assert outcome.kind == kind and (row.state, row.note) == (state, note)
    assert len(rig.backend.writes) == 1  # never sent again
    assert rig.backend.lookups == ([outcome.request_id] if lookup else [])
    entries = rig.runner.record(CALL_ID).entries()
    if kind == "done":
        assert outcome.line.text == f"Done, your number is {ISSUED}." and len(entries) == 1
        assert isinstance(rig.events[0], ActionCompleted)
    else:
        assert outcome.line.text == "I could not confirm it went through." and entries == ()
        assert ISSUED not in outcome.line.text and "two zero" not in outcome.line.spoken
        [event] = rig.events
        assert isinstance(event, ActionUnconfirmed) and event.kind == "unknown"


@pytest.mark.parametrize("lookup", [True, False], ids=["with a lookup", "without"])
def test_a_reply_that_comes_late_changes_nothing_said_and_is_never_sent_again(
    lookup: bool, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    rig = Rig("late", lookup=lookup)

    async def scenario() -> tuple[Any, OutboxEntry]:
        outcome = await rig.confirmed_run(advance_s=20.0)
        await rig.clock.advance(15.0)  # the write's own reply comes at 30 s
        await until(rig.backend.finished.is_set)
        await until(lambda: "action_replied_late" in caplog.text)
        return outcome, await _row(rig, outcome.request_id)

    outcome, row = asyncio.run(scenario())
    assert outcome.kind == "unknown" and row.state == "flagged"
    assert len(rig.backend.writes) == 1 and rig.runner.record(CALL_ID).entries() == ()
    assert rig.backend.lookups == ([outcome.request_id] if lookup else [])


@pytest.mark.parametrize("mode", ["answer", "reject"])
def test_the_same_confirmed_action_twice_is_carried_out_once(mode: Mode) -> None:
    rig = Rig(mode)

    async def scenario() -> tuple[Any, Any]:
        confirmed = confirmed_of(await rig.plan())
        return await rig.run(confirmed), await rig.run(confirmed)

    first, second = asyncio.run(scenario())
    assert len(rig.backend.writes) == 1
    assert first.request_id == second.request_id and first.kind == second.kind
    assert len(rig.events) == 1  # the second says its row's outcome, with no event
    assert len(rig.runner.record(CALL_ID).entries()) == (1 if mode == "answer" else 0)


def test_a_stop_never_cuts_a_write_in_half() -> None:
    """Invariant 6: cancelling the wait for a job (a stop, a barge-in, the call's end) leaves
    the write to run to its end, its row marked and its record kept."""
    rig = Rig("gated")

    async def scenario() -> tuple[bool, OutboxEntry]:
        waiting = asyncio.ensure_future(rig.confirmed_run())
        await until(lambda: bool(rig.backend.writes))
        waiting.cancel()
        await asyncio.sleep(0)
        rig.backend.gate.set()
        await until(lambda: bool(rig.runner.record(CALL_ID).entries()))
        [entry] = rig.runner.record(CALL_ID).entries()
        await until(lambda: bool(rig.events))
        return waiting.cancelled(), await _row(rig, entry.request_id)

    cancelled, row = asyncio.run(scenario())
    assert cancelled and row.state == "done" and len(rig.backend.writes) == 1
    assert isinstance(rig.events[0], ActionCompleted)


def test_anything_but_a_confirmed_action_the_yes_rule_issued_is_refused() -> None:
    """Invariant 1: a copy of a confirmed action, a read-back, or a tool call's arguments
    claiming a yes are refused before anything is written or sent."""
    rig = Rig()

    async def scenario() -> list[str]:
        plan = await rig.plan()
        confirmed = confirmed_of(plan)
        told = []
        for forged in (confirmed.model_copy(), plan, {"action": "open_request", "yes": True}):
            with pytest.raises(TypeError) as raised:
                await rig.run(forged)  # type: ignore[arg-type]
            told.append(str(raised.value))
        return told

    told = asyncio.run(scenario())
    assert told == [NOT_CONFIRMED] * 3
    assert asyncio.run(rig.outbox.entries()) == () and rig.backend.writes == []


def test_each_calls_record_holds_only_its_own_writes() -> None:
    rig = Rig()

    async def scenario() -> None:
        await rig.run(confirmed_of(await rig.plan()))

    asyncio.run(scenario())
    assert len(rig.runner.record(CALL_ID).entries()) == 1
    assert rig.runner.record("call-2").entries() == ()
    kept = rig.runner.record(CALL_ID)
    rig.runner.forget(CALL_ID)
    assert rig.runner.record(CALL_ID) is not kept and rig.runner.record(CALL_ID).entries() == ()


def test_a_runner_given_a_record_fills_that_one_and_keeps_it() -> None:
    """Block 0's `record=` (TextCall's one call): the jobs and the talker's guard share it."""
    rig = Rig()
    given = ActionRecord()
    rig.runner = ActionRunner([rig.action], outbox=rig.outbox, record=given)
    outcome = asyncio.run(rig.confirmed_run())
    [entry] = given.entries()
    assert outcome.kind == "done" and entry.request_id == outcome.request_id
    assert rig.runner.record(CALL_ID) is given and rig.runner.record("call-2") is given
    rig.runner.forget(CALL_ID)
    assert rig.runner.record(CALL_ID) is given and len(given.entries()) == 1


@pytest.mark.parametrize("mode", ["reject", "not_sent", "raise"])
def test_nothing_shown_holds_a_drafts_value_or_a_backends_reason(
    mode: Mode, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    rig = Rig(mode, lookup=False)
    outcome = asyncio.run(rig.confirmed_run())
    surfaces = {
        **shown(caplog=caplog),
        "outcome": repr(outcome),
        "line": outcome.line.text + outcome.line.spoken,
        "events": repr(rig.events),
    }
    assert holding(SUMMARY, surfaces) == [] and holding(REASON, surfaces) == []


def test_an_outbox_that_cannot_be_written_means_nothing_is_sent() -> None:
    class Full(MemoryOutbox):
        async def add(self, entry: OutboxEntry) -> bool:
            raise OSError("disk full")

    rig = Rig(outbox=Full())
    outcome = asyncio.run(rig.confirmed_run())
    assert outcome.kind == "failed" and rig.backend.writes == []
    assert rig.runner.record(CALL_ID).entries() == ()


def test_a_row_that_cannot_be_marked_keeps_the_outcome_said() -> None:
    class Stuck(MemoryOutbox):
        async def mark(self, request_id: str, **_: Any) -> None:
            raise OSError("disk")

    rig = Rig(outbox=Stuck())
    outcome = asyncio.run(rig.confirmed_run())
    assert outcome.kind == "done" and len(rig.runner.record(CALL_ID).entries()) == 1
    row = asyncio.run(rig.outbox.get(outcome.request_id))
    assert row is not None and row.state == "sending"  # left for reconcile at the next start


def test_a_draft_the_action_cannot_read_back_is_never_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spoken_lines, "default_action_lines", lambda tag: LIBRARY)
    rig = Rig()

    async def scenario() -> Any:
        plan = await rig.plan()
        changed = plan.model_copy(update={"draft_json": '{"category": "furniture"}'})
        return await rig.run(confirmed_of(changed))

    outcome = asyncio.run(scenario())
    assert outcome.kind == "failed" and outcome.line.text == "Library failed."
    assert rig.backend.writes == [] and asyncio.run(rig.outbox.entries()) == ()


def test_a_done_line_the_result_cannot_fill_says_the_librarys_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from t2_agentic_voice.actions import action_job
    from t2_agentic_voice.domain.action_declaration import Say

    monkeypatch.setattr(action_job, "default_action_lines", lambda tag: LIBRARY)
    rig = Rig(done=Say(en="{number}", ar="{number}"))
    rig.backend.mode = "odd"
    rig.action = rig.action.replaced(execute=_blank_number)
    rig.runner = type(rig.runner)([rig.action], outbox=rig.outbox)
    outcome = asyncio.run(rig.confirmed_run())
    assert outcome.kind == "done" and outcome.line.text == "Library unknown."
    assert len(rig.runner.record(CALL_ID).entries()) == 1


def test_a_job_that_fails_in_the_library_is_logged_by_its_type(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from t2_agentic_voice.actions import action_job

    async def broken(*_: Any) -> Any:
        raise RuntimeError(SUMMARY)

    monkeypatch.setattr(action_job, "write", broken)
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    rig = Rig()
    with pytest.raises(RuntimeError):
        asyncio.run(rig.confirmed_run())
    [record] = [r for r in caplog.records if r.getMessage() == "action_job_failed"]
    assert record.fields["failure"] == "RuntimeError"  # type: ignore[attr-defined]
    assert holding(SUMMARY, shown(caplog=caplog)) == []


async def _blank_number(draft: Any) -> Any:
    from tests.t2_agentic_voice.actions.action_support import RequestOpened

    return RequestOpened(number=" ")
