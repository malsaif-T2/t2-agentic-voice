"""The chat model port and the knowledge port (domain/ports/chat_model.py, knowledge.py; plan 006,
Block 0): each request, message, event and passage a frozen model checked at the boundary
(invariant 4), refusing what the provider or a team could get wrong; a tool call's arguments kept
as the raw text the model wrote, for the tool runner to parse."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.domain.ports.chat_model import (
    ChatMessage,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
)
from t2_agentic_voice.domain.ports.knowledge import Passage

CALL = ToolCallRequest(id="call-1", name="search_help", arguments='{"query": "reset password"')
SCHEMA = ToolSchema(
    name="search_help",
    description="Search the help articles.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
)


def test_a_request_holds_its_messages_tools_and_the_models_settings() -> None:
    messages = (
        ChatMessage.system("Answer briefly."),
        ChatMessage.user("How do I reset my password?"),
        ChatMessage.assistant(tool_calls=(CALL,)),
        ChatMessage.tool_result("call-1", '{"passages": []}'),
        ChatMessage.assistant("I found nothing on that."),
    )
    request = ChatRequest(
        messages=messages,
        tools=(SCHEMA,),
        model="openai/gpt-oss-120b",
        reasoning_effort="low",
        max_output_tokens=1024,
        temperature=0.2,
    )
    assert [m.role for m in request.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert request.messages[2].tool_calls[0].arguments == '{"query": "reset password"'  # raw
    assert request.messages[3].tool_call_id == "call-1"
    with pytest.raises(ValidationError):
        request.model = "other"  # type: ignore[misc]


def test_the_events_and_a_passage_load() -> None:
    assert TextDelta(text="Open").text == "Open"
    assert Usage(input_tokens=900, output_tokens=40, cached_tokens=512).cached_tokens == 512
    assert Done(finish_reason="tool_calls").finish_reason == "tool_calls"
    passage = Passage(
        id="p-7", title="Reset a password", text="...", steps=("Open", "Reset"), score=0.82
    )
    assert (passage.steps, passage.source) == (("Open", "Reset"), None)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (ChatMessage, {"role": "user", "content": ""}),  # says nothing
        (ChatMessage, {"role": "user", "content": "x", "tool_calls": [CALL]}),
        (ChatMessage, {"role": "tool", "content": "x"}),  # names no call
        (ChatMessage, {"role": "assistant", "content": "x", "tool_call_id": "c"}),
        (ChatMessage, {"role": "developer", "content": "x"}),
        (ToolCallRequest, {"id": "", "name": "x"}),
        (ToolCallRequest, {"id": "c", "name": "two words"}),
        (ToolSchema, {"name": "x", "description": "d", "parameters": {"type": "array"}}),
        (ToolSchema, {"name": "x", "description": ""}),
        (ChatRequest, {"messages": [], "model": "m"}),
        (ChatRequest, {"messages": [ChatMessage.user("x")], "model": ""}),
        (
            ChatRequest,
            {"messages": [ChatMessage.user("x")], "model": "m", "tools": [SCHEMA, SCHEMA]},
        ),
        (
            ChatRequest,
            {"messages": [ChatMessage.user("x")], "model": "m", "reasoning_effort": "max"},
        ),
        (ChatRequest, {"messages": [ChatMessage.user("x")], "model": "m", "temperature": 3}),
        (ChatRequest, {"messages": [ChatMessage.user("x")], "model": "m", "max_output_tokens": 0}),
        (TextDelta, {"text": ""}),
        (Usage, {"input_tokens": 1, "output_tokens": -1}),
        (Usage, {"input_tokens": 1, "output_tokens": 1, "cached_tokens": 2}),
        (Done, {"finish_reason": "cancelled"}),
        (Passage, {"id": "p", "title": "t", "text": "x", "score": float("nan")}),
        (Passage, {"id": "", "title": "t", "text": "x", "score": 0.5}),
        (Passage, {"id": "p", "title": "t", "text": "x", "score": 0.5, "source": ""}),
    ],
)
def test_a_wrong_value_is_refused(model: type[Any], values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)
