"""Each job's action moves through the lifecycle's table (actions/action_job.py's `Flow`,
domain/action_flow.py's `advance`): a job's moves, however its write ends, are the table's own,
so none is refused; a move the table refuses is logged as `action_flow_refused`, by the call,
the action, the state and the event alone, and never raised into the call."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from t2_agentic_voice.actions import action_job
from t2_agentic_voice.actions.action_job import Flow
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.domain.action_flow import ActionState, FlowEvent, advance
from t2_agentic_voice.domain.ports.outbox import OutboxEntry

from tests.leaks import holding, shown
from tests.t2_agentic_voice.actions.action_support import SUMMARY, Mode, Rig

REFUSED = "action_flow_refused"


def _moves(monkeypatch: pytest.MonkeyPatch) -> list[tuple[ActionState, FlowEvent]]:
    """The moves the jobs ask of the table, each still made by it."""
    asked: list[tuple[ActionState, FlowEvent]] = []

    def spied(state: ActionState, event: FlowEvent) -> ActionState:
        asked.append((state, event))
        return advance(state, event)

    monkeypatch.setattr(action_job, "advance", spied)
    return asked


@pytest.mark.parametrize(
    ("mode", "lookup", "advance_s", "moves"),
    [
        ("answer", True, 0.0, [("confirmed", "sent"), ("sending", "returned")]),
        ("reject", True, 0.0, [("confirmed", "sent"), ("sending", "refused")]),
        ("lost_reply", True, 20.0, [("confirmed", "sent"), ("sending", "found")]),
        ("raise", False, 0.0, [("confirmed", "sent"), ("sending", "lost")]),
    ],
)
def test_a_jobs_moves_are_the_tables_and_none_is_refused(
    mode: Mode,
    lookup: bool,
    advance_s: float,
    moves: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    asked = _moves(monkeypatch)
    rig = Rig(mode, lookup=lookup)
    asyncio.run(rig.confirmed_run(advance_s=advance_s))
    assert asked == moves
    assert REFUSED not in caplog.text


def test_nothing_sent_is_refused_from_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Full(MemoryOutbox):
        async def add(self, entry: OutboxEntry) -> bool:
            raise OSError("disk full")

    asked = _moves(monkeypatch)
    outcome = asyncio.run(Rig(outbox=Full()).confirmed_run())
    assert outcome.kind == "failed" and asked == [("confirmed", "refused")]


def test_a_move_the_table_refuses_is_logged_by_its_names_and_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    flow = Flow("call-1", "open_request", state="done")
    flow.move("sent")
    assert flow.state == "done"
    [record] = [r for r in caplog.records if r.getMessage() == REFUSED]
    assert record.levelno == logging.ERROR
    fields: dict[str, Any] = dict(record.fields)  # type: ignore[attr-defined]
    assert fields == {
        "call_id": "call-1",
        "action": "open_request",
        "state": "done",
        "flow_event": "sent",
    }


def test_a_job_whose_move_is_refused_still_ends_as_it_would(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")

    def refusing(state: ActionState, event: FlowEvent) -> ActionState:
        raise ValueError(f"an action in state {state} has no move on {event}")

    monkeypatch.setattr(action_job, "advance", refusing)
    rig = Rig()
    outcome = asyncio.run(rig.confirmed_run())
    assert outcome.kind == "done" and len(rig.backend.writes) == 1
    refused = [r for r in caplog.records if r.getMessage() == REFUSED]
    assert len(refused) == 2  # sent, then returned
    assert holding(SUMMARY, shown(caplog=caplog)) == []
