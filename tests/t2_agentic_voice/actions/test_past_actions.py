"""What a caller had done (actions/tools.py's `CallContext.past_actions`, the action runner's
`past`; plan 007's Q4): the outbox's `done` rows of the action, in any call, oldest first, their
results parsed; scoped to the verified caller, whose subject is the context's own and never an
argument (invariant 3, GP-08), as a tool in a talker's turn reads it; a context with no reader
reads its call's record alone; and a row whose result cannot be read is left out, logged by
the action's name alone."""

from __future__ import annotations

import asyncio
import inspect
from datetime import timedelta
from typing import Any

import pytest
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.tools import CallContext, RecordedAction, tool
from t2_agentic_voice.agent.context import call_context
from t2_agentic_voice.agent.talker import ToolEnded
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

from tests.t2_agentic_voice.actions.action_support import Backend, an_action
from tests.t2_agentic_voice.agent.action_talk_support import acting, fake_rule_a
from tests.t2_agentic_voice.agent.chat_support import CALLER, FakeChat, call, calls, reply, said
from tests.t2_agentic_voice.fakes import WALL_START, FakeClock

OTHER = "made-up-other-subject"
SECRET_NUMBER = "2026111082000777"


def _row(
    n: int, subject: str, state: OutboxState, result: str | None, **changes: Any
) -> OutboxEntry:
    at = WALL_START + timedelta(minutes=n)
    values: dict[str, Any] = {
        "request_id": f"r-{n}",
        "call_id": f"call-{n}",
        "subject": subject,
        "action": "open_request",
        "draft_json": '{"category": "software", "summary": "made up"}',
        "state": state,
        "result_json": result,
        "created_at": at,
        "updated_at": at,
    }
    return OutboxEntry.model_validate(values | changes)


def _outbox(*rows: OutboxEntry) -> MemoryOutbox:
    store = MemoryOutbox()
    for row in rows:
        assert asyncio.run(store.add(row))
    return store


ROWS = (
    _row(1, CALLER.subject, "done", '{"number": "2026111082000101"}'),
    _row(2, OTHER, "done", f'{{"number": "{SECRET_NUMBER}"}}'),
    _row(3, CALLER.subject, "flagged", None),
    _row(4, CALLER.subject, "done", '{"number": "2026111082000104"}'),
    _row(5, CALLER.subject, "done", '{"number": "2026111082000105"}', action="other_action"),
)


def _runner(store: MemoryOutbox) -> ActionRunner:
    return ActionRunner([an_action(Backend(outbox=store, clock=FakeClock()))], outbox=store)


def test_a_callers_done_rows_of_the_action_oldest_first_their_results_parsed() -> None:
    runner = _runner(_outbox(*ROWS))
    ctx = call_context(caller=CALLER, call_id="c", language="en", actions=runner, record=None)
    assert asyncio.run(ctx.past_actions("open_request")) == (
        RecordedAction(
            action="open_request", request_id="r-1", result={"number": "2026111082000101"}
        ),
        RecordedAction(
            action="open_request", request_id="r-4", result={"number": "2026111082000104"}
        ),
    )


def test_another_callers_rows_are_never_read_whoever_the_context_names() -> None:
    """Invariant 3 (GP-08): `past_actions` takes the action alone, so no argument can name a
    caller; a context is the verified caller's, and a copy keeps its caller's reader."""
    runner = _runner(_outbox(*ROWS))
    assert list(inspect.signature(CallContext.past_actions).parameters) == ["self", "action"]
    mine = call_context(caller=CALLER, call_id="c", language="en", actions=runner, record=None)
    found = asyncio.run(mine.past_actions("open_request"))
    assert SECRET_NUMBER not in str(found)
    theirs = call_context(
        caller=Caller(subject=OTHER), call_id="c", language="en", actions=runner, record=None
    )
    assert [done.request_id for done in asyncio.run(theirs.past_actions("open_request"))] == ["r-2"]


def test_a_tool_reads_only_its_callers_past_actions_in_a_talkers_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rule_a(monkeypatch)
    read: list[tuple[RecordedAction, ...]] = []

    @tool(description="List the caller's made-up requests.", reports_on=["open_request"])
    async def my_requests(ctx: CallContext) -> list[str]:
        done = await ctx.past_actions("open_request")
        read.append(done)
        return [each.request_id for each in done]

    model = FakeChat(calls(call("my_requests")), said("You have two."))
    rig = acting(model, my_requests, outbox=_outbox(*ROWS))
    events = reply(rig.talker, TalkerTurn(turn_id=1, words="What have I opened?", language="en"))
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.ok and ended.result == '["r-1", "r-4"]'
    assert SECRET_NUMBER not in str(read)


def test_a_context_with_no_reader_reads_its_calls_record_alone() -> None:
    record = (
        RecordedAction(action="open_request", request_id="r-9", result={"number": "1"}),
        RecordedAction(action="other_action", request_id="r-8"),
    )
    ctx = CallContext(caller=CALLER, call_id="c", language="en", record=record)
    assert asyncio.run(ctx.past_actions("open_request")) == record[:1]


def test_a_row_whose_result_cannot_be_read_is_left_out_logged_by_the_action_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unreadable = _row(6, CALLER.subject, "done", f"{{{SECRET_NUMBER} not json")
    runner = _runner(_outbox(ROWS[0], unreadable))
    assert [r.request_id for r in asyncio.run(runner.past(CALLER.subject, "open_request"))] == [
        "r-1"
    ]
    assert "outbox_result_unreadable" in caplog.text and SECRET_NUMBER not in caplog.text
