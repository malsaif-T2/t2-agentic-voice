"""The action runner's caps (actions/action_runner.py; the design's 6.4): `max_per_call` in this
call and `per_caller_per_day` for the verified caller in the last day, each checked in `propose`
before the read-back and counted over the outbox's rows, which only a confirmed action writes,
never over proposals. Only a row whose write may have reached the system counts (`sending`,
`done`, `flagged`), never one the system refused (`rejected`) or that was never sent
(`not_sent`), so the caller may try again (the owner's ruling of 2026-11-10)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from t2_agentic_voice.actions.action_runner import PER_CALL, PER_DAY, ActionRunner
from t2_agentic_voice.actions.tools import CallContext, ToolResult
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CALLER,
    Mode,
    Rig,
    confirmed_of,
    context,
    request,
)

CAPPED_IN_CALL = ToolResult(data={"error": PER_CALL}, ok=False, failure="cap_per_call")
CAPPED_TODAY = ToolResult(data={"error": PER_DAY}, ok=False, failure="cap_per_caller")
# How each refused write ends in the outbox: the backend's refusal, or a write never sent.
REFUSED: dict[Mode, OutboxState] = {"reject": "rejected", "not_sent": "not_sent"}


def _daily(rig: Rig, per_day: int) -> Rig:
    rig.runner = ActionRunner([rig.action], outbox=rig.outbox, per_caller_per_day=per_day)
    return rig


def test_the_per_call_cap_counts_confirmed_actions_never_proposals() -> None:
    rig = Rig(max_per_call=1)

    async def scenario() -> tuple[Any, Any, Any, Any]:
        first = await rig.plan()
        again = await rig.plan()  # a proposal counts for nothing
        await rig.run(confirmed_of(first))
        capped = await rig.runner.propose(request(), context(), clock=rig.clock)
        other_call = await rig.runner.propose(request(), context(call_id="call-2"), clock=rig.clock)
        return first, again, capped, other_call

    first, again, capped, other_call = asyncio.run(scenario())
    assert isinstance(first, ReadBackPlan) and isinstance(again, ReadBackPlan)
    assert capped == CAPPED_IN_CALL  # a done write blocks a second
    assert isinstance(other_call, ReadBackPlan)


@pytest.mark.parametrize("refused", list(REFUSED))
def test_a_write_refused_or_never_sent_leaves_the_caller_a_second_try_in_the_call(
    refused: Mode,
) -> None:
    """With `max_per_call` 1, the second try is read back and written; once it is done, a
    third is refused."""
    rig = Rig(refused, max_per_call=1)

    async def scenario() -> tuple[Any, Any, Any, Any]:
        failed = await rig.run(confirmed_of(await rig.plan()))
        rig.backend.mode = "answer"
        again = await rig.runner.propose(request(), context(), clock=rig.clock)
        done = None
        if isinstance(again, ReadBackPlan):  # a new read-back: a new reply and a new yes
            done = await rig.run(confirmed_of(again, reply_id=5, turn_id=10))
        third = await rig.runner.propose(request(), context(), clock=rig.clock)
        return failed, again, done, third

    failed, again, done, third = asyncio.run(scenario())
    assert failed.kind == "failed" and isinstance(again, ReadBackPlan)
    assert done is not None and done.kind == "done" and len(rig.backend.writes) == 2
    states = [row.state for row in asyncio.run(rig.outbox.entries())]
    assert states == [REFUSED[refused], "done"]
    assert third == CAPPED_IN_CALL


def test_a_write_said_unknown_holds_its_place_in_the_call() -> None:
    """A write that raised and that the lookup did not find may have been done: its row is
    `flagged`, the caller hears `unknown`, and a second try is refused."""
    rig = Rig("raise", max_per_call=1)

    async def scenario() -> tuple[Any, Any]:
        unknown = await rig.run(confirmed_of(await rig.plan()))
        rig.backend.mode = "answer"
        return unknown, await rig.runner.propose(request(), context(), clock=rig.clock)

    unknown, again = asyncio.run(scenario())
    assert unknown.kind == "unknown"
    assert [row.state for row in asyncio.run(rig.outbox.entries())] == ["flagged"]
    assert again == CAPPED_IN_CALL and len(rig.backend.writes) == 1


@pytest.mark.parametrize(
    ("state", "counted"),
    [
        ("sending", True),
        ("done", True),
        ("flagged", True),
        ("rejected", False),
        ("not_sent", False),
    ],
)
def test_each_cap_counts_a_row_only_when_its_write_may_have_reached_the_system(
    state: OutboxState, counted: bool
) -> None:
    """A row under way or whose reply never came (`sending`), one `done`, and one `flagged` for
    a person (no reply and no lookup hit) each count toward both caps; a `rejected` or
    `not_sent` one, definitely not done, counts toward neither."""
    rig = _daily(Rig(max_per_call=1), per_day=1)
    at = rig.clock.wall()
    row = OutboxEntry(
        request_id="r-1",
        call_id=CALL_ID,
        subject=CALLER.subject,
        action=rig.action.name,
        draft_json="{}",
        state=state,
        created_at=at,
        updated_at=at,
    )

    async def scenario() -> tuple[Any, Any]:
        await rig.outbox.add(row)
        this_call = await rig.runner.propose(request(), context(), clock=rig.clock)
        next_call = await rig.runner.propose(request(), context(call_id="call-2"), clock=rig.clock)
        return this_call, next_call

    this_call, next_call = asyncio.run(scenario())
    if counted:
        assert (this_call, next_call) == (CAPPED_IN_CALL, CAPPED_TODAY)
    else:
        assert isinstance(this_call, ReadBackPlan) and isinstance(next_call, ReadBackPlan)


@pytest.mark.parametrize("refused", list(REFUSED))
def test_the_per_caller_cap_counts_a_days_writes_that_may_have_reached_the_system(
    refused: Mode,
) -> None:
    """With a daily cap of 1, a refused or never-sent write in one call leaves the caller's
    place, so the next call's write is read back and done; that one fills it, for this caller
    alone, until a day has passed."""
    rig = _daily(Rig(refused, max_per_call=5), per_day=1)
    someone_else = CallContext(
        caller=Caller(subject="someone-else"), call_id="call-4", language="en"
    )

    async def scenario() -> list[Any]:
        told: list[Any] = []
        for call_id, mode in (("call-1", refused), ("call-2", "answer"), ("call-3", "answer")):
            rig.backend.mode = mode
            plan = await rig.runner.propose(request(), context(call_id=call_id), clock=rig.clock)
            told.append(plan)
            if isinstance(plan, ReadBackPlan):
                told.append((await rig.run(confirmed_of(plan), call_id=call_id)).kind)
        told.append(await rig.runner.propose(request(), someone_else, clock=rig.clock))
        await rig.clock.advance(24 * 3600.0 + 1.0)
        told.append(await rig.runner.propose(request(), context(call_id="call-5"), clock=rig.clock))
        return told

    first, failed, second, done, third, other_caller, next_day = asyncio.run(scenario())
    assert isinstance(first, ReadBackPlan) and failed == "failed"
    assert isinstance(second, ReadBackPlan) and done == "done"
    assert third == CAPPED_TODAY
    assert isinstance(other_caller, ReadBackPlan) and isinstance(next_day, ReadBackPlan)
