"""The stubs plan 007's Block 0 left for Track B, each raising with the track's name. Track B
deletes this file as it fills them."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from t2_agentic_voice.actions.action import action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry

AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
TRACK = "Track B"
CONTEXT = CallContext(caller=Caller(subject="m"), call_id="c", language="en")


def _entry() -> OutboxEntry:
    return OutboxEntry(
        request_id="r-1",
        call_id="c-1",
        subject="made-up",
        action="open_request",
        draft_json='{"summary": "made up"}',
        created_at=AT,
        updated_at=AT,
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda store: store.add(_entry()),
        lambda store: store.mark("r-1", state="done"),
        lambda store: store.get("r-1"),
        lambda store: store.entries(),
        lambda store: store.count(subject="s", action="a", since=AT),
        lambda store: store.aclose(),
    ],
    ids=["add", "mark", "get", "entries", "count", "aclose"],
)
@pytest.mark.parametrize("store", [MemoryOutbox(), SqliteOutbox()], ids=["memory", "sqlite"])
def test_the_outboxes_are_stubs(store: Outbox, call: Callable[[Outbox], Any]) -> None:
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(call(store))


def test_the_sqlite_outbox_opens_nothing_yet(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(SqliteOutbox.open(tmp_path / "outbox.sqlite3"))


def test_the_record_is_a_stub() -> None:
    record = ActionRecord()
    with pytest.raises(NotImplementedError, match=TRACK):
        record.add(action="x", request_id="r", result_json="{}", evidence=(), at=1.0)
    with pytest.raises(NotImplementedError, match=TRACK):
        record.entries()


class _Draft(BaseModel):
    summary: str


class _Result(BaseModel):
    id: str


async def _open_request(draft: _Draft) -> _Result:
    return _Result(id="1")


def test_the_action_runner_is_a_stub_that_tells_its_schemas() -> None:
    made = action(
        name="open_request",
        description="x",
        read_back=ReadBack({"en": ("{summary}", "?")}),
        done=Say(en="{id}"),
        claims=Claims({"en": ["c"]}),
    )(_open_request)
    runner = ActionRunner([made], outbox=MemoryOutbox())
    assert [schema.name for schema in runner.schemas()] == ["open_request"]
    request = ToolCallRequest(id="t-1", name="open_request", arguments="{}")
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(runner.propose(request, CONTEXT))
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(runner.reconcile())


def test_past_actions_is_a_stub() -> None:
    with pytest.raises(NotImplementedError, match=TRACK):
        asyncio.run(CONTEXT.past_actions("open_request"))
