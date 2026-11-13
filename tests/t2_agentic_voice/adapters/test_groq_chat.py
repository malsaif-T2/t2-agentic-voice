"""GroqChat's stream (adapters/groq_chat.py) on a fake transport: the request
as Groq takes it (every kind of message, the tools, the model's settings, `reasoning_effort`
only to a model that takes it), and the events in order (the text as it comes and never the
reasoning, each tool call whole however its pieces came, the usage with and without cached
tokens, one `Done`). Its failures are tested in test_groq_chat_errors.py. Nothing leaves the
machine."""

from __future__ import annotations

import asyncio
from typing import Any, get_args

import httpx
import pytest
from t2_agentic_voice.core.settings.llm import REASONING_MODELS, LlmModel
from t2_agentic_voice.domain.ports.chat_model import (
    ChatMessage,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    Usage,
)

from tests.t2_agentic_voice.adapters.chat_support import (
    CACHED,
    REQUEST,
    USAGE,
    ask,
    body_of,
    call_piece,
    chunk,
    sse,
    streamed,
    text,
)
from tests.t2_agentic_voice.adapters.groq_support import FakeGroq

Reply = httpx.Response | Exception


def _events(reply: Reply, request: ChatRequest = REQUEST) -> tuple[list[Any], FakeGroq]:
    fake = FakeGroq(reply)
    return asyncio.run(ask(fake, request)), fake


def test_the_request_holds_every_message_the_tools_and_the_models_settings() -> None:
    request = REQUEST.model_copy(
        update={"reasoning_effort": "low", "max_output_tokens": 300, "temperature": 0.4}
    )
    _, fake = _events(streamed(sse(*text("Hi."))), request)
    (sent,) = fake.requests
    assert str(sent.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert sent.content.startswith(b'{"messages":')
    assert body_of(sent) == {
        "messages": [
            {"role": "system", "content": "Answer in one short sentence."},
            {"role": "user", "content": "How do I reset my password?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_0",
                        "type": "function",
                        "function": {"name": "search_help", "arguments": '{"query":"made up"}'},
                    }
                ],
            },
            {"role": "tool", "content": "Open Settings, then Security.", "tool_call_id": "call_0"},
            {"role": "assistant", "content": "Open Settings."},
            {"role": "user", "content": "And then?"},
        ],
        "model": "openai/gpt-oss-120b",
        "max_completion_tokens": 300,
        "reasoning_effort": "low",
        "stream": True,
        "temperature": 0.4,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_help",
                    "description": "Search the help articles.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ],
    }


def test_what_the_request_leaves_out_is_not_sent() -> None:
    bare = ChatRequest(messages=(ChatMessage.user("Hi"),), model="openai/gpt-oss-20b")
    _, fake = _events(streamed(sse(*text("Hi."))), bare)
    assert body_of(fake.requests[0]) == {
        "messages": [{"role": "user", "content": "Hi"}],
        "model": "openai/gpt-oss-20b",
        "stream": True,
    }


@pytest.mark.parametrize(
    ("model", "sent"),
    [
        ("openai/gpt-oss-120b", True),
        ("openai/gpt-oss-20b", True),
        ("llama-3.3-70b-versatile", False),  # Groq refuses the field for the Llama models
        ("llama-3.1-8b-instant", False),
    ],
)
def test_reasoning_effort_goes_only_to_a_model_that_takes_it(model: str, sent: bool) -> None:
    request = REQUEST.model_copy(update={"model": model, "reasoning_effort": "medium"})
    _, fake = _events(streamed(sse(*text("Hi."))), request)
    body = body_of(fake.requests[0])
    assert ("reasoning_effort" in body, body.get("reasoning_effort")) == (
        sent,
        "medium" if sent else None,
    )


def test_the_closed_list_names_the_gpt_oss_models_of_the_settings() -> None:
    models: tuple[str, ...] = get_args(LlmModel)
    assert {name for name in models if name.startswith("openai/gpt-oss")} == REASONING_MODELS


def test_the_text_streams_piece_by_piece_and_never_the_reasoning() -> None:
    events, _ = _events(streamed(sse(*text("Open", " Settings", ", then Security.")), size=7))
    assert events == [
        TextDelta(text="Open"),
        TextDelta(text=" Settings"),
        TextDelta(text=", then Security."),
        Usage(input_tokens=822, output_tokens=68),
        Done(finish_reason="stop"),
    ]


def test_a_tool_call_split_over_several_deltas_comes_whole_once_it_has_ended() -> None:
    pieces = [
        call_piece(0, id="call_7", type="function", name="search_help", arguments=""),
        call_piece(0, arguments='{"que'),
        call_piece(0, arguments='ry": "reset'),
        call_piece(0, arguments=' password"}'),
    ]
    end = chunk(finish="tool_calls", x_groq={"usage": CACHED})
    events, _ = _events(streamed(sse(chunk({"role": "assistant"}), *pieces, end), size=5))
    assert events == [
        ToolCallRequest(id="call_7", name="search_help", arguments='{"query": "reset password"}'),
        Usage(input_tokens=822, output_tokens=68, cached_tokens=768),
        Done(finish_reason="tool_calls"),
    ]


def test_two_tool_calls_come_in_their_order_after_the_text_before_them() -> None:
    pieces = [
        chunk({"content": "Let me check."}),
        call_piece(1, id="call_b", name="open_ticket", arguments='{"kind":'),
        call_piece(0, id="call_a", name="search_help", arguments='{"query":"x"}'),
        call_piece(1, arguments=' "help"}'),
        chunk(finish="tool_calls"),
    ]
    events, _ = _events(streamed(sse(*pieces)))
    assert events == [
        TextDelta(text="Let me check."),
        ToolCallRequest(id="call_a", name="search_help", arguments='{"query":"x"}'),
        ToolCallRequest(id="call_b", name="open_ticket", arguments='{"kind": "help"}'),
        Done(finish_reason="tool_calls"),
    ]


@pytest.mark.parametrize(
    ("usage", "where", "expected"),
    [
        (USAGE, "x_groq", Usage(input_tokens=822, output_tokens=68)),
        (CACHED, "x_groq", Usage(input_tokens=822, output_tokens=68, cached_tokens=768)),
        (CACHED, "usage", Usage(input_tokens=822, output_tokens=68, cached_tokens=768)),
        (
            USAGE | {"prompt_tokens_details": None},
            "usage",
            Usage(input_tokens=822, output_tokens=68),
        ),
    ],
)
def test_the_usage_of_the_last_chunk_comes_before_done(
    usage: dict[str, Any], where: str, expected: Usage
) -> None:
    last = {"x_groq": {"usage": usage}} if where == "x_groq" else {"usage": usage}
    # Groq's own last chunk may come after the finish, with no choice at all.
    end = [
        chunk(finish="stop"),
        {"id": "c", "object": "chat.completion.chunk", "choices": [], **last},
    ]
    events, _ = _events(streamed(sse(chunk({"content": "Hi."}), *end)))
    assert events == [TextDelta(text="Hi."), expected, Done(finish_reason="stop")]


def test_no_usage_reported_gives_no_usage_and_function_call_reads_as_tool_calls() -> None:
    pieces = [call_piece(0, id="call_1", name="search_help", arguments="{}")]
    events, _ = _events(streamed(sse(*pieces, chunk(finish="function_call"))))
    assert events == [
        ToolCallRequest(id="call_1", name="search_help", arguments="{}"),
        Done(finish_reason="tool_calls"),
    ]


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_each_finish_reason_is_kept(reason: str) -> None:
    events, _ = _events(streamed(sse(*text("Open Settings", finish=reason))))
    assert events[-1] == Done.model_validate({"finish_reason": reason})


def test_an_answer_with_only_its_end_gives_done_alone() -> None:
    events, _ = _events(
        streamed(sse(chunk({"role": "assistant", "content": ""}), chunk(finish="stop")))
    )
    assert events == [Done(finish_reason="stop")]
