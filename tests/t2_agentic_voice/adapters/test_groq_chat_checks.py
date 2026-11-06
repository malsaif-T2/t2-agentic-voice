"""GroqChat's checks (adapters/groq_chat.py; plan 006, Track A): a cancel, or a stream closed
between events, that stops within 50 ms and leaves no task or connection; one connection kept
open between two requests, and the five-minute keep-alive on its own pool (the prototype's D41);
`llm.timeout_s` bounding the whole request without ever cancelling the consumer; and the request
hook's `Accept`, `Content-Type` and body checked against the SDK's own streamed chat request
(groq 1.7.0), `GROQ_*` variables changing nothing. Real connections only to servers on
127.0.0.1; nothing leaves the machine."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.adapters.groq_client import AsyncGroq
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, TextDelta

from tests.t2_agentic_voice.adapters.chat_support import (
    REQUEST,
    Local,
    Server,
    ask,
    chat_settings,
    chunk,
    settle,
    sse,
    text,
)
from tests.t2_agentic_voice.adapters.groq_support import KEY, OTHER, FakeGroq

ANSWER = sse(*text("Open Settings."))


@pytest.mark.parametrize("how", ["cancel_before_the_answer", "cancel_mid_stream", "close"])
def test_a_stopped_stream_ends_at_once_and_closes_its_connection(how: str) -> None:
    """The port's rule (the design's 6.1): a request stopped while it waits for Groq's answer,
    while it waits for the next chunk, or closed between events, ends in 50 ms, leaving no task
    and no connection."""
    first = sse(chunk({"content": "Open"}), done=False)
    server = Server(None if how == "cancel_before_the_answer" else first, stalling=True)

    async def scenario(transport: Local) -> tuple[float, list[ChatEvent], set[asyncio.Task[Any]]]:
        adapter = GroqChat.from_settings(chat_settings(), transport=transport)
        stream = cast("AsyncGenerator[ChatEvent, None]", adapter.stream(REQUEST))
        seen = [] if how == "cancel_before_the_answer" else [await anext(stream)]
        if how == "close":
            start = time.perf_counter()
            await stream.aclose()
        else:
            waiting = asyncio.create_task(anext(stream))
            async with asyncio.timeout(5):
                while not server.answered.is_set():
                    await asyncio.sleep(0.001)
            await asyncio.sleep(0.05)  # the next read is on the wire, its answer awaited
            start = time.perf_counter()
            waiting.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiting
        took = time.perf_counter() - start
        left = await settle()
        assert await asyncio.to_thread(server.hung_up.wait, 5)  # before aclose: the stop closed it
        await adapter.aclose()
        return took, seen, left

    with server as transport:
        took, seen, left = asyncio.run(scenario(transport))
    expected = [] if how == "cancel_before_the_answer" else [TextDelta(text="Open")]
    assert (seen, left, transport.closed) == (expected, set(), True)
    assert took < 0.05, f"the stop took {took * 1000:.1f} ms"


def test_two_requests_go_over_one_connection_kept_open() -> None:
    """The prototype's D41: reconnecting cost about 1 s a reply, so the second request takes the
    connection the first left open."""
    server = Server(ANSWER)

    async def scenario(transport: Local) -> list[list[ChatEvent]]:
        adapter = GroqChat.from_settings(chat_settings(), transport=transport)
        try:
            return [[event async for event in adapter.stream(REQUEST)] for _ in range(2)]
        finally:
            await adapter.aclose()

    with server as transport:
        first, second = asyncio.run(scenario(transport))
        assert server.hung_up.wait(5)  # by aclose
    assert first == second and first[0] == TextDelta(text="Open Settings.")
    assert (server.connections, server.requests) == (1, 2)


def test_the_adapters_own_pool_keeps_an_idle_connection_five_minutes() -> None:
    """httpx's default would close it after 5 s idle; the shared client's limits keep it 300 s.
    Read from the pool the client built itself (no transport given), with no request sent."""
    adapter = GroqChat.from_settings(chat_settings())
    transport = vars(vars(adapter)["_groq"]._client)["_transport"]
    pool = vars(transport)["_pool"]
    assert vars(pool)["_keepalive_expiry"] == 300.0
    asyncio.run(adapter.aclose())


def test_the_timeout_bounds_the_whole_request_not_each_read() -> None:
    """A Groq that keeps sending a piece every 0.1 s never trips a read's timeout; the request's
    deadline, `llm.timeout_s`, ends it as a retryable timeout."""

    async def trickle() -> AsyncIterator[bytes]:
        while True:
            yield sse(chunk({"content": "and "}), done=False)
            await asyncio.sleep(0.1)

    fake = FakeGroq(httpx.Response(200, content=trickle()))
    start = time.perf_counter()
    with pytest.raises(ProviderError) as raised:
        asyncio.run(ask(fake, timeout_s=0.3))
    took = time.perf_counter() - start
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)
    # The deadline runs on the loop's clock, which ticks every 15.6 ms on Windows.
    assert 0.3 - 0.016 <= took < 2.0


def test_the_deadline_never_cancels_the_consumer_between_events() -> None:
    """The consumer's own wait outlives the deadline untouched; the stream then fails at its
    next wait for Groq, never inside the consumer's code."""

    async def slow() -> AsyncIterator[bytes]:
        yield sse(chunk({"content": "Open"}), done=False)
        await asyncio.sleep(5)
        yield ANSWER

    fake = FakeGroq(httpx.Response(200, content=slow()))

    async def scene() -> tuple[bool, ProviderError | None]:
        adapter = GroqChat.from_settings(chat_settings(timeout_s=0.1), transport=fake)
        stream = adapter.stream(REQUEST)
        await anext(stream)
        slept = False
        try:
            await asyncio.sleep(0.2)  # past the deadline
            slept = True
            await anext(stream)
        except ProviderError as error:
            return slept, error
        finally:
            await adapter.aclose()
        return slept, None

    slept, error = asyncio.run(scene())
    assert slept and error is not None and error.kind == "timeout"


async def _sdk_request(fake: FakeGroq) -> None:
    """The SDK's own streamed chat request, with no hook, for the same messages."""
    client = AsyncGroq(
        api_key=KEY,
        base_url="https://api.groq.com",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=fake),
    )
    try:
        messages = [{"role": "user", "content": "How do I reset my password?"}]
        await client.chat.completions.create(
            messages=messages,  # type: ignore[arg-type]
            model="openai/gpt-oss-120b",
            stream=True,
        )
    finally:
        await client.close()


def test_the_hook_sends_what_the_sdk_itself_sends_for_a_streamed_chat() -> None:
    """groq 1.7.0 sends JSON as the `Accept` of a streamed chat and builds its body messages
    first: the hook's `Accept`, `Content-Type` and the body's opening are the SDK's own."""
    from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatRequest

    sdk, ours = FakeGroq(httpx.Response(200)), FakeGroq(httpx.Response(200, content=ANSWER))
    asyncio.run(_sdk_request(sdk))
    request = ChatRequest(
        messages=(ChatMessage.user("How do I reset my password?"),), model="openai/gpt-oss-120b"
    )
    asyncio.run(ask(ours, request))
    (theirs,), (sent,) = sdk.requests, ours.requests
    for name in ("accept", "content-type"):
        assert sent.headers[name] == theirs.headers[name] == "application/json"
    assert sent.content == theirs.content and sent.content.startswith(b'{"messages":')


SHELLS = [
    {"GROQ_API_KEY": OTHER, "GROQ_BASE_URL": "https://elsewhere.example"},
    {"GROQ_CUSTOM_HEADERS": f"authorization: Bearer {OTHER}\nAccept: text/event-stream"},
    {"GROQ_CUSTOM_HEADERS": "content-type: multipart/form-data"},  # beside the SDK's: still JSON
    {"GROQ_CUSTOM_HEADERS": "X-Stainless-Raw-Response: stream"},
]


@pytest.mark.parametrize("shell", SHELLS)
def test_the_sdks_own_variables_change_nothing(
    shell: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plain, shelled = (
        FakeGroq(httpx.Response(200, content=ANSWER)),
        FakeGroq(httpx.Response(200, content=ANSWER)),
    )
    want = asyncio.run(ask(plain))
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    got = asyncio.run(ask(shelled))
    (sent,), (asked,) = plain.requests, shelled.requests
    assert asked.headers.multi_items() == sent.headers.multi_items()
    assert (str(asked.url), asked.content) == (str(sent.url), sent.content)
    assert got == want


def test_built_in_code_with_its_own_values_it_streams_too() -> None:
    adapter = GroqChat(
        api_key=SecretStr(KEY),
        base_url="https://api.groq.com",
        timeout_s=8.0,
        transport=FakeGroq(httpx.Response(200, content=ANSWER)),
    )

    async def scene() -> list[ChatEvent]:
        try:
            return [event async for event in adapter.stream(REQUEST)]
        finally:
            await adapter.aclose()

    assert asyncio.run(scene())[0] == TextDelta(text="Open Settings.")
