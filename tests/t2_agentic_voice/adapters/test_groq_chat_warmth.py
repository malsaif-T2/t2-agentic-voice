"""GroqChat's warmth (adapters/groq_chat.py, the `ConnectionWarmth` and `WarmUp` ports): whether
its next request goes out on a kept-alive connection, from its own record of its last request;
its warm request, a GET of the model list; and, under `warmup.after_cancel`, the fresh connection
it opens in the background after a cancelled stream (TD-115). On a fake transport and a fake
clock; nothing leaves the machine."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import cast

import httpx
import pytest
from t2_agentic_voice.adapters import groq_chat
from t2_agentic_voice.adapters.groq_chat import GroqChat
from t2_agentic_voice.adapters.groq_client import LIMITS
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.warmup import WarmupSettings
from t2_agentic_voice.domain.ports.chat_model import ChatEvent
from t2_agentic_voice.domain.ports.connection_warmth import ConnectionWarmth, WarmUp

from tests.t2_agentic_voice.adapters.chat_support import REQUEST, chat_settings, sse, streamed, text
from tests.t2_agentic_voice.adapters.groq_support import KEY, FakeGroq


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(groq_chat, "monotonic", fake)
    return fake


def _answer() -> httpx.Response:
    return streamed(sse(*text("Open ", "Settings.")), size=16)


async def _read(adapter: GroqChat, *, first_only: bool = False) -> None:
    # GroqChat's stream is an async generator, which a close between events ends at once.
    stream = cast(AsyncGenerator[ChatEvent, None], adapter.stream(REQUEST))
    try:
        async for _ in stream:
            if first_only:
                break
    finally:
        await stream.aclose()


def _adapter(*replies: httpx.Response | Exception) -> GroqChat:
    return GroqChat.from_settings(chat_settings(), transport=FakeGroq(*replies))


def test_it_is_cold_before_any_request_and_warm_after_a_stream_that_ended(clock: _Clock) -> None:
    adapter = _adapter(_answer())
    assert not adapter.warm()
    asyncio.run(_read(adapter))
    assert adapter.warm()
    expiry = LIMITS.keepalive_expiry
    assert expiry == 300.0
    clock.now += expiry - 1
    assert adapter.warm()
    clock.now += 1
    assert not adapter.warm()  # the pool has let that connection go
    asyncio.run(adapter.aclose())


def test_it_is_cold_after_a_stream_that_failed(clock: _Clock) -> None:
    adapter = _adapter(_answer(), httpx.Response(500, json={"error": {"message": "x"}}))
    asyncio.run(_read(adapter))
    assert adapter.warm()
    with pytest.raises(ProviderError):
        asyncio.run(_read(adapter))
    assert not adapter.warm()
    asyncio.run(adapter.aclose())


def test_it_is_cold_after_a_stream_closed_between_its_events(clock: _Clock) -> None:
    adapter = _adapter(_answer(), _answer())
    asyncio.run(_read(adapter))
    assert adapter.warm()
    asyncio.run(_read(adapter, first_only=True))  # a cancel closes that connection
    assert not adapter.warm()
    asyncio.run(adapter.aclose())


def test_it_is_cold_after_a_cancelled_stream(clock: _Clock) -> None:
    release = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return _answer()

    adapter = GroqChat.from_settings(chat_settings(), transport=FakeGroq(_answer(), slow))

    async def run() -> None:
        await _read(adapter)
        assert adapter.warm()
        task = asyncio.create_task(_read(adapter))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert not adapter.warm()
    asyncio.run(adapter.aclose())


def test_the_groq_chat_adapter_is_a_connection_warmth_and_a_warm_up() -> None:
    adapter = _adapter()
    warmth: ConnectionWarmth = adapter
    warm_up: WarmUp = adapter
    assert isinstance(warmth, ConnectionWarmth) and isinstance(warm_up, WarmUp)
    asyncio.run(adapter.aclose())


MODELS = {"object": "list", "data": []}


def test_its_warm_up_is_one_bodiless_get_of_the_model_list_and_leaves_it_warm(
    clock: _Clock,
) -> None:
    fake = FakeGroq(httpx.Response(200, json=MODELS))
    adapter = GroqChat.from_settings(chat_settings(), transport=fake)
    asyncio.run(adapter.warm_up())
    (request,) = fake.requests
    assert (request.method, request.url.path, request.content) == ("GET", "/openai/v1/models", b"")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert adapter.warm()
    asyncio.run(adapter.aclose())


def test_a_failed_warm_up_is_a_provider_error_holding_no_key(clock: _Clock) -> None:
    adapter = _adapter(httpx.Response(401, json={"error": {"message": KEY}}))
    with pytest.raises(ProviderError) as raised:
        asyncio.run(adapter.warm_up())
    assert raised.value.kind == "rejected" and KEY not in repr(raised.value.details)
    assert not adapter.warm()
    asyncio.run(adapter.aclose())


async def _sent(fake: FakeGroq, count: int) -> None:
    async with asyncio.timeout(5):
        while len(fake.requests) < count:
            await asyncio.sleep(0.01)


def _cancel_one(
    adapter: GroqChat, fake: FakeGroq, done: Callable[[], bool] = lambda: False
) -> None:
    """One stream cancelled once its request is out, then the adapter closed once `done` holds
    (or after 50 ms, for a reopen that should not come)."""

    async def run() -> None:
        task = asyncio.create_task(_read(adapter))
        await _sent(fake, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with asyncio.timeout(5):
            await asyncio.sleep(0.05)
            while not done():
                await asyncio.sleep(0.01)
        await adapter.aclose()

    asyncio.run(run())


def _hanging(release: asyncio.Event) -> object:
    async def slow(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return _answer()

    return slow


def test_by_default_a_cancelled_stream_opens_no_fresh_connection(clock: _Clock) -> None:
    """GP-18's characterization of the default: `warmup.after_cancel` off, nothing is sent."""
    assert chat_settings().warmup.after_cancel is False
    fake = FakeGroq(_hanging(asyncio.Event()), httpx.Response(200, json=MODELS))  # type: ignore[arg-type]
    _cancel_one(GroqChat.from_settings(chat_settings(), transport=fake), fake, lambda: True)
    assert [request.method for request in fake.requests] == ["POST"]


def test_after_a_cancelled_stream_it_opens_a_fresh_connection_in_the_background(
    clock: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    settings = chat_settings().model_copy(update={"warmup": WarmupSettings(after_cancel=True)})
    fake = FakeGroq(_hanging(asyncio.Event()), httpx.Response(200, json=MODELS))  # type: ignore[arg-type]
    adapter = GroqChat.from_settings(settings, transport=fake)

    async def run() -> None:
        task = asyncio.create_task(_read(adapter))
        await _sent(fake, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(_reopened(caplog), timeout=5)
        assert adapter.warm()
        await adapter.aclose()

    asyncio.run(run())
    assert [(r.method, r.url.path) for r in fake.requests][1] == ("GET", "/openai/v1/models")


async def _reopened(caplog: pytest.LogCaptureFixture) -> None:
    while not any(r.getMessage() == "chat_reopened" for r in caplog.records):
        await asyncio.sleep(0.01)


def test_a_failed_reopen_is_logged_by_its_kind_and_the_close_stops_one_in_flight(
    clock: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    settings = chat_settings().model_copy(update={"warmup": WarmupSettings(after_cancel=True)})
    failing = FakeGroq(_hanging(asyncio.Event()), httpx.Response(500, json={"error": KEY}))  # type: ignore[arg-type]
    _cancel_one(
        GroqChat.from_settings(settings, transport=failing),
        failing,
        lambda: any(r.getMessage() == "chat_reopen_failed" for r in caplog.records),
    )
    (line,) = [r for r in caplog.records if r.getMessage() == "chat_reopen_failed"]
    assert getattr(line, FIELDS) == {"error": "server_error"}
    assert KEY not in caplog.text
    held = FakeGroq(_hanging(asyncio.Event()), _hanging(asyncio.Event()))  # type: ignore[arg-type]
    adapter = GroqChat.from_settings(settings, transport=held)
    _cancel_one(adapter, held, lambda: len(held.requests) == 2)  # the close stops the reopen
    assert [request.method for request in held.requests] == ["POST", "GET"]
