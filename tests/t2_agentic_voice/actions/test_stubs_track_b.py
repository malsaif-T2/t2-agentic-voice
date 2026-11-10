"""The stubs plan 007's Block 0 left for Track B, each raising with the track's name. Track B
deletes this file as it fills them."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel
from t2_agentic_voice.actions.action import action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

TRACK = "Track B"
CONTEXT = CallContext(caller=Caller(subject="m"), call_id="c", language="en")


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
