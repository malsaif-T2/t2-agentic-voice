"""OpenAIChat's stream (adapters/openai_chat.py, D-112) on a fake transport: the request as
OpenAI's Chat Completions take it (every kind of message, the tools with parallel calls, the
model's settings, `reasoning_effort` only to a model that takes it, the usage asked for), the
events in order (the text as it comes, each tool call whole however its pieces came, the usage
from the last chunk, one `Done`), its failures (a refused status, an error inside the stream,
a chunk it cannot read, a stream cut short, a deadline), the key held to the settings' rules,
and the warmth of its connection. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.openai_chat import OpenAIChat
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.core.settings.provider_keys import OpenAISettings
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    Usage,
)

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.chat_support import (
    CACHED,
    REQUEST,
    USAGE,
    body_of,
    call_piece,
    chunk,
    sse,
    streamed,
)
from tests.t2_agentic_voice.adapters.groq_support import FakeGroq

KEY = "sk-made-up-key-0123456789abcdefghijklmnop"
LUNA = REQUEST.model_copy(update={"model": "gpt-6-luna", "reasoning_effort": "none"})


def _settings(timeout_s: float = 8.0, **openai: Any) -> VoiceSettings:
    given = OpenAISettings(**({"api_key": SecretStr(KEY)} | openai))
    return VoiceSettings(env="test", openai=given, llm=LlmSettings(timeout_s=timeout_s))


def _usage(usage: dict[str, Any] = USAGE) -> dict[str, Any]:
    """OpenAI's last chunk under `include_usage`: no choice, the usage."""
    return chunk() | {"choices": [], "usage": usage}


def _words(*pieces: str, finish: str = "stop") -> bytes:
    return sse(
        chunk({"role": "assistant", "content": ""}, usage=None),
        *(chunk({"content": piece}, usage=None) for piece in pieces),
        chunk(finish=finish, usage=None),
        _usage(),
    )


async def _ask(fake: httpx.AsyncBaseTransport, request: ChatRequest = LUNA, **given: Any) -> Any:
    adapter = OpenAIChat.from_settings(_settings(**given), transport=fake)
    seen: list[ChatEvent] = []
    try:
        async for event in adapter.stream(request):
            seen.append(event)
    except ProviderError as error:
        return seen, error
    finally:
        await adapter.aclose()
    return seen, None


def _events(reply: Any, request: ChatRequest = LUNA) -> tuple[list[ChatEvent], FakeGroq]:
    fake = FakeGroq(reply)
    seen, error = asyncio.run(_ask(fake, request))
    assert error is None, error
    return seen, fake


def test_the_request_holds_every_message_the_tools_and_the_models_settings() -> None:
    request = LUNA.model_copy(update={"max_output_tokens": 300, "temperature": 0.4})
    _, fake = _events(streamed(_words("Hi.")), request)
    (sent,) = fake.requests
    assert str(sent.url) == "https://api.openai.com/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.headers["accept"] == "text/event-stream"
    body = body_of(sent)
    assert [m["role"] for m in body["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert body["messages"][2]["tool_calls"][0]["function"] == {
        "name": "search_help",
        "arguments": '{"query":"made up"}',
    }
    assert body["messages"][3] == {
        "role": "tool",
        "content": "Open Settings, then Security.",
        "tool_call_id": "call_0",
    }
    assert body["tools"][0]["function"]["name"] == "search_help"
    rest = {k: v for k, v in body.items() if k not in ("messages", "tools")}
    assert rest == {
        "model": "gpt-6-luna",
        "stream": True,
        "stream_options": {"include_usage": True},
        "parallel_tool_calls": True,
        "max_completion_tokens": 300,
        "temperature": 0.4,
        "reasoning_effort": "none",
    }


@pytest.mark.parametrize(("model", "sent"), [("gpt-5.5", True), ("gpt-4.1", False)])
def test_an_effort_goes_to_gpt_5_5_and_none_to_gpt_4_1(model: str, sent: bool) -> None:
    request = REQUEST.model_copy(update={"model": model, "reasoning_effort": "none"})
    _, fake = _events(streamed(_words("Hi.")), request)
    body = body_of(fake.requests[0])
    assert body.get("reasoning_effort") == ("none" if sent else None)  # gpt-4.1 refuses it


def test_a_value_left_out_is_not_sent_nor_an_effort_to_a_model_that_takes_none() -> None:
    request = REQUEST.model_copy(
        update={"model": "gpt-made-up", "tools": (), "reasoning_effort": "none"}
    )
    _, fake = _events(streamed(_words("Hi.")), request)
    body = body_of(fake.requests[0])
    assert set(body) == {"model", "messages", "stream", "stream_options"}


def test_the_events_come_in_order_with_each_tool_call_whole_and_the_usage() -> None:
    answer = sse(
        chunk({"role": "assistant", "content": "Let me "}),
        chunk({"content": "check."}),
        call_piece(0, id="call_1", type="function", name="search_help", arguments=""),
        call_piece(1, id="call_2", type="function", name="search_help", arguments='{"qu'),
        call_piece(0, arguments='{"query":"a"}'),
        call_piece(1, arguments='ery":"b"}'),
        chunk(finish="tool_calls"),
        _usage(CACHED),
        b": a comment line\n\n",
    )
    events, _ = _events(streamed(answer, size=7))
    assert events == [
        TextDelta(text="Let me "),
        TextDelta(text="check."),
        ToolCallRequest(id="call_1", name="search_help", arguments='{"query":"a"}'),
        ToolCallRequest(id="call_2", name="search_help", arguments='{"query":"b"}'),
        Usage(input_tokens=822, output_tokens=68, cached_tokens=768),
        Done(finish_reason="tool_calls"),
    ]


def _failure(reply: Any, request: ChatRequest = LUNA) -> tuple[list[ChatEvent], ProviderError]:
    seen, error = asyncio.run(_ask(FakeGroq(reply), request))
    assert error is not None
    return seen, error


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [(401, "rejected", False), (400, "rejected", False), (500, "server_error", True)],
)
def test_a_refused_status_names_openai_and_never_the_body(
    status: int, kind: str, retryable: bool
) -> None:
    body = {"error": {"message": "the made-up request said sk-secret", "code": "x"}}
    _, error = _failure(httpx.Response(status, json=body))
    assert (error.kind, error.retryable) == (kind, retryable)
    assert error.details == {"provider": "OpenAI", "error": "HTTPStatusError", "status": status}
    assert holding("sk-secret", shown(error)) == [] and holding(KEY, shown(error)) == []


def test_a_rate_limit_waits_as_its_retry_after_says() -> None:
    _, error = _failure(httpx.Response(429, headers={"retry-after": "2"}, json={}))
    assert (error.kind, error.retryable, error.retry_after_s) == ("rate_limited", True, 2.0)


def test_an_error_inside_the_stream_is_rejected_with_its_code_when_a_plain_name() -> None:
    plain = sse(chunk({"content": "Hi"}), {"error": {"code": "server_overloaded", "message": "m"}})
    seen, error = _failure(streamed(plain))
    assert seen == [TextDelta(text="Hi")]
    assert (error.kind, error.details) == (
        "rejected",
        {"provider": "OpenAI", "error": "stream_error", "code": "server_overloaded"},
    )
    odd = sse({"error": {"code": "the made-up request: sk-secret"}})
    _, error = _failure(streamed(odd))
    assert error.details == {"provider": "OpenAI", "error": "stream_error"}
    assert holding("sk-secret", shown(error)) == []


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"data: {not json\n\n", "unreadable_chunk"),
        (b"data: [1, 2]\n\n", "unreadable_chunk"),
        (sse(chunk({"content": "Hi"})), "no_finish"),
    ],
)
def test_an_answer_it_cannot_read_or_one_cut_short_is_a_server_error(
    body: bytes, reason: str
) -> None:
    _, error = _failure(streamed(body))
    assert (error.kind, error.retryable, error.details["error"]) == ("server_error", False, reason)


def test_a_stream_that_stalls_past_the_deadline_is_a_timeout() -> None:
    async def stalled(request: httpx.Request) -> httpx.Response:
        async def pieces() -> Any:
            yield sse(chunk({"content": "Hi"}), done=False)
            await asyncio.sleep(5)

        return httpx.Response(200, content=pieces())

    seen, error = asyncio.run(_ask(FakeGroq(stalled), timeout_s=0.2))
    assert seen == [TextDelta(text="Hi")]
    assert error is not None and (error.kind, error.retryable) == ("timeout", True)


def test_the_key_and_base_url_are_held_to_the_settings_rules() -> None:
    with pytest.raises(ConfigurationError, match="T2V_OPENAI__API_KEY") as raised:
        OpenAIChat.from_settings(VoiceSettings(env="test"))
    assert "llm.provider to groq" in raised.value.message
    with pytest.raises(ConfigurationError, match="T2V_OPENAI__BASE_URL"):
        OpenAIChat(api_key=SecretStr(KEY), base_url="http://api.openai.com/v1", timeout_s=8)
    with pytest.raises(ConfigurationError, match="T2V_OPENAI__API_KEY"):
        OpenAIChat(api_key=SecretStr("  "), base_url="https://api.openai.com/v1", timeout_s=8)


def test_a_connection_is_warm_after_a_whole_answer_and_cold_after_a_failure() -> None:
    async def run() -> list[bool]:
        replies = [
            httpx.Response(200, json={"data": []}),
            streamed(_words("Hi.")),
            httpx.Response(500, json={}),
        ]
        fake = FakeGroq(*replies)
        adapter = OpenAIChat.from_settings(_settings(), transport=fake)
        seen = [adapter.warm()]
        await adapter.warm_up()
        seen.append(adapter.warm())
        _ = [event async for event in adapter.stream(LUNA)]
        seen.append(adapter.warm())
        with pytest.raises(ProviderError):
            _ = [event async for event in adapter.stream(LUNA)]
        seen.append(adapter.warm())
        (models, *_) = fake.requests
        assert (models.method, str(models.url)) == ("GET", "https://api.openai.com/v1/models")
        assert models.headers["authorization"] == f"Bearer {KEY}"
        await adapter.aclose()
        return seen

    assert asyncio.run(run()) == [False, True, True, False]


def test_a_stream_closed_midway_leaves_the_connection_cold() -> None:
    async def run() -> bool:
        adapter = OpenAIChat.from_settings(_settings(), transport=FakeGroq(streamed(_words("a"))))
        stream = adapter.stream(LUNA)
        assert await anext(stream) == TextDelta(text="a")
        await stream.aclose()  # type: ignore[attr-defined]
        warm = adapter.warm()
        await adapter.aclose()
        return warm

    assert asyncio.run(run()) is False


def test_the_repr_shows_no_key() -> None:
    adapter = OpenAIChat.from_settings(_settings(), transport=FakeGroq())
    assert KEY not in repr(adapter) and json.dumps(adapter.data_flow.model_dump())
    asyncio.run(adapter.aclose())
