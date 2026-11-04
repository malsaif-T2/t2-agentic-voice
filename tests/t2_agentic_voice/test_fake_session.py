"""The fake session holds its lock as `CallSession` does (tests/t2_agentic_voice/fake_session.py),
so a `Commands.run` that calls the session back or does not return fails a test (TD-068); and the
slow work that answers a turn (responder_fakes.py) is held mid-flight on the fake clock and
cancelled there, as the cancel scope's tests need."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.voice.protocol import State
from t2_agentic_voice.voice.session.commands import Command, Send
from t2_agentic_voice.voice.session.session_events import Connected

from tests.t2_agentic_voice.fake_session import RUN_S, FakeSession
from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.responder_fakes import CHUNKS, SlowResponder
from tests.t2_agentic_voice.session_fakes import FakeSessionIO


class _CallsBack:
    """`Commands` that break io.py's rule: `run` calls the session back from inside."""

    def __init__(self) -> None:
        self.session: FakeSession | None = None

    async def run(self, command: Command) -> None:
        assert self.session is not None
        await self.session.handle(Connected(at=0.0))


class _Waits:
    """`Commands` whose `run` waits until `go` is set, or `forever`."""

    def __init__(self, *, forever: bool = False) -> None:
        self.go = asyncio.Event()
        self.forever = forever
        self.ran: list[Command] = []

    async def run(self, command: Command) -> None:
        self.ran.append(command)
        if self.forever:
            await asyncio.sleep(3600)
        await self.go.wait()


def test_the_fake_session_holds_its_lock_and_fails_a_run_that_breaks_ios_rule(
    settings: VoiceSettings,
) -> None:
    """TD-068: a `run` that calls the session back fails at once, one that does not return
    fails after `run_s`, and each step waits for the one before it to release the lock."""
    io, hello = FakeSessionIO(settings), Send(message=State(state="listening"))
    calls_back = _CallsBack()
    calls_back.session = FakeSession(io.setup, calls_back)
    waits = _Waits(forever=True)
    stuck = FakeSession(io.setup, waits, run_s=0.01)
    held = _Waits()
    serial = FakeSession(io.setup, held, replies=lambda event: [hello])

    async def call() -> None:
        session = calls_back.session
        assert session is not None
        with pytest.raises(RuntimeError, match=r"called the session's handle.*TD-068"):
            await session.give(hello)
        with pytest.raises(RuntimeError, match=r"did not return within 0.01 s.*FIX: "):
            await stuck.give(hello)
        first = asyncio.create_task(serial.handle(Connected(at=1.0)))
        second = asyncio.create_task(serial.handle(Connected(at=2.0)))
        for _ in range(5):
            await asyncio.sleep(0)
        assert [event.at for event in serial.events] == [1.0]  # the second waits on the lock
        held.go.set()
        await asyncio.gather(first, second)
        await serial.aclose()

    asyncio.run(call())
    assert [event.at for event in serial.events] == [1.0, 2.0] and serial.closed
    assert held.ran == [hello, hello] and waits.ran == [hello] and RUN_S == 5.0


def test_the_slow_responder_is_held_on_the_fake_clock_and_cancelled_there() -> None:
    """Its stream and its lookup sleep on the fake clock: they finish when it has moved far
    enough, and a cancel mid-flight is recorded at the clock's time."""
    clock = FakeClock(start=0.0)
    whole, stopped = SlowResponder(clock), SlowResponder(clock, chunk_s=2.0, lookup_s=9.0)

    async def call() -> tuple[str, str]:
        text = asyncio.create_task(whole.read())
        found = asyncio.create_task(whole.lookup("a made-up query"))
        cut = [asyncio.create_task(stopped.read()), asyncio.create_task(stopped.lookup("q"))]
        await clock.advance(0.0)  # each starts, and sleeps
        await clock.advance(5.0)
        for task in cut:
            task.cancel()
        results = await asyncio.gather(*cut, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        return await text, await found

    assert asyncio.run(call()) == (" ".join(CHUNKS), "found for a made-up query")
    assert (whole.started, whole.finished, whole.cancelled) == (
        {"stream": 0.0, "lookup": 0.0},
        {"stream": 3.0, "lookup": 5.0},
        {},
    )
    assert (stopped.finished, stopped.cancelled) == ({}, {"stream": 5.0, "lookup": 5.0})
