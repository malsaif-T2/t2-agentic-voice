"""The tools' shapes (actions/tools.py, runner.py, knowledge.py; plan 006, Block 0): a `Tool`
loads with the design's fields and refuses what it cannot run with; a bound parameter names a
field of the verified caller and is never one the talker fills; `CallContext` holds the caller
read-only; `ToolError` has its stable code; and every behaviour Track B builds is a stub that
raises: `@tool`, `Tool.from_function`, `tool_schema`, `FromCaller.value`, the runner, which
runs a call on the call's clock, and `knowledge_tool`."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from t2_agentic_voice.actions.knowledge import knowledge_tool
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import (
    CallContext,
    FromCaller,
    Tool,
    ToolResult,
    from_caller,
    tool,
)
from t2_agentic_voice.core.errors import T2VoiceError, ToolError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.talker_declaration import DeclaredTool
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

from tests.t2_agentic_voice.fakes import FakeClock

CALLER = Caller(subject="made-up-subject", attributes={"department": "it"})


class Lookup(BaseModel):
    asset_tag: str


async def lookup(asset_tag: str, employee_id: str) -> dict[str, str]:
    return {"asset_tag": asset_tag, "owner": employee_id}


def _tool(**changes: Any) -> Tool:
    values: dict[str, Any] = {
        "name": "lookup_device",
        "description": "Find a device by its asset tag.",
        "parameters": Lookup,
        "function": lookup,
        "bind": {"employee_id": from_caller("subject")},
    }
    return Tool.model_validate(values | changes)


def test_a_tool_holds_the_designs_fields_and_is_the_declarations_shape() -> None:
    found = _tool(progress="searching", timeout_s=3.0, progress_after_s=0.8)
    assert (found.on_interrupt, found.timeout_s, found.progress_after_s) == ("cancel", 3.0, 0.8)
    assert found.bind == {"employee_id": FromCaller(field="subject")}
    assert isinstance(found, DeclaredTool)
    with pytest.raises(TypeError):
        found.bind["x"] = from_caller("locale")  # type: ignore[index]
    with pytest.raises(ValidationError):
        found.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "look up"},
        {"name": ""},
        {"description": " "},
        {"timeout_s": 0},
        {"progress": "Searching"},
        {"progress": "searching", "progress_after_s": 5.0},  # never before the timeout
        {"on_interrupt": "pause"},
        {"bind": {"asset_tag": from_caller("subject")}},  # the talker's own parameter
        {"parameters": dict},
        {"function": "lookup"},
    ],
)
def test_a_tool_it_cannot_run_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _tool(**changes)


def test_a_bound_parameter_names_a_field_of_the_caller() -> None:
    assert from_caller("attributes.department").field == "attributes.department"
    for field in ["password", "attributes.", "subject.name", ""]:
        with pytest.raises(ValidationError):
            from_caller(field)


def test_a_tool_sees_the_caller_read_only_and_returns_a_result() -> None:
    ctx = CallContext(caller=CALLER, call_id="call-1", language="ar-SA")
    with pytest.raises(ValidationError):
        ctx.caller = Caller(subject="someone-else")  # type: ignore[misc]
    result = ToolResult(
        data={"status": "active"}, card=Card(title="Laptop"), evidence=("LT-00423",)
    )
    assert (result.data, result.evidence) == ({"status": "active"}, ("LT-00423",))
    with pytest.raises(ValidationError):
        CallContext(caller=CALLER, call_id="call 1", language="ar-SA")
    error = ToolError("No device with that tag is assigned to you.")
    assert isinstance(error, T2VoiceError) and error.code == "tool_error"


def test_every_behaviour_track_b_builds_is_a_stub_that_raises() -> None:
    found = _tool()
    with pytest.raises(NotImplementedError):
        tool(description="Find a device.")
    with pytest.raises(NotImplementedError):
        Tool.from_function(lookup, description="Find a device.")
    with pytest.raises(NotImplementedError):
        found.tool_schema()
    with pytest.raises(NotImplementedError):
        from_caller("subject").value(CALLER)
    runner = ToolRunner([found])
    assert runner.tools == (found,)
    with pytest.raises(NotImplementedError):
        runner.schemas()
    request = ToolCallRequest(id="c-1", name="lookup_device", arguments="{}")
    ctx = CallContext(caller=CALLER, call_id="call-1", language="en")
    with pytest.raises(NotImplementedError):
        asyncio.run(runner.run(request, ctx, clock=FakeClock()))
    with pytest.raises(NotImplementedError):
        knowledge_tool(FakeKnowledgeBase(), description="Search the help articles.")
