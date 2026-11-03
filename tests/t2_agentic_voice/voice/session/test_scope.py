"""Each reply's cancel scope (voice/session/scope.py), driven with the slow responder
(tests/t2_agentic_voice/responder_fakes.py) on the fake clock: a cancel ends a slow model stream
and a slow lookup at once, well within its bound, leaving no task; work started outside the scope
goes on; a scope cancelled starts nothing; a task that will not end is left to end on its own once
the bound has passed, logged by its name; a task's failure is logged by its kind; and a task that
cancels its own scope does not wait on itself. The session's stops are test_overlap_stop.py's."""

from __future__ import annotations

import asyncio
import inspect
import logging

import pytest
from t2_agentic_voice.voice.session.scope import CANCEL_WAIT_S, CancelScope

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.responder_fakes import SlowResponder


def _others() -> set[asyncio.Task[object]]:
    """Every task of the loop but the test's own."""
    return asyncio.all_tasks() - {asyncio.current_task()}


def test_a_cancel_ends_a_slow_stream_and_a_slow_lookup_at_once_and_leaves_no_task() -> None:
    clock = FakeClock()
    responder, outside = SlowResponder(clock), SlowResponder(clock, lookup_s=2.0)
    scope = CancelScope(name="reply-1", clock=clock)

    async def call() -> None:
        stream = scope.start(responder.read(), name="model")
        lookup = scope.start(responder.lookup("made-up order"), name="lookup")
        elsewhere = asyncio.create_task(outside.lookup("made-up write"))
        await asyncio.sleep(0)  # each begins, and sleeps on the clock
        await clock.advance(1.5)  # one chunk read, the lookup still waiting
        assert (scope.running, scope.cancelled) == (2, False)
        stopped_at = clock.now()
        await scope.cancel()
        assert (scope.running, scope.cancelled) == (0, True)
        assert stream.cancelled() and lookup.cancelled()
        assert responder.cancelled == {"stream": stopped_at, "lookup": stopped_at}
        assert max(responder.cancelled.values()) - stopped_at <= CANCEL_WAIT_S
        assert _others() == {elsewhere}  # no task of the scope is left
        await clock.advance(1.0)
        assert await elsewhere == "found for made-up write"  # work outside the scope goes on
        assert not _others()

    asyncio.run(call())


def test_a_scope_cancelled_starts_nothing_and_one_with_nothing_running_waits_on_nothing() -> None:
    clock = FakeClock()
    scope = CancelScope(name="reply-2", clock=clock)

    async def call() -> None:
        await scope.cancel()
        assert scope.cancelled and clock.sleeps == []  # nothing to wait on
        work = SlowResponder(clock).read()
        task = scope.start(work, name="model")
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled() and scope.running == 0
        assert inspect.getcoroutinestate(work) == "CORO_CLOSED"  # closed, never run

    asyncio.run(call())


def test_a_task_that_will_not_end_is_left_once_the_bound_passes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A task that swallows its cancellation (as a lookup in a worker thread would run on) is
    waited on for the bound alone, on the call's clock, then left to end on its own, still
    counted; it ends later, and nothing is left."""
    clock = FakeClock()
    scope = CancelScope(name="reply-3", clock=clock, wait_s=0.05)

    async def stubborn(done: asyncio.Event) -> str:
        try:
            await clock.sleep(10.0)
        except asyncio.CancelledError:
            await done.wait()
        return "ended on its own"

    async def call() -> None:
        done = asyncio.Event()
        task = scope.start(stubborn(done), name="worker-lookup")
        await asyncio.sleep(0)
        cancelling = asyncio.create_task(scope.cancel())
        for _ in range(5):  # the cancel runs until it waits on the bound
            await asyncio.sleep(0)
        assert not cancelling.done() and clock.sleeps[-1] == 0.05
        await clock.advance(0.05)
        await asyncio.wait_for(cancelling, timeout=5)
        assert scope.running == 1 and not task.done()
        done.set()
        assert await task == "ended on its own"
        assert scope.running == 0 and not _others()

    caplog.set_level(logging.INFO)
    asyncio.run(call())
    (left,) = [r for r in caplog.records if r.getMessage() == "scope_tasks_left"]
    assert getattr(left, "fields", None) == {"scope": "reply-3", "tasks": ["worker-lookup"]}


def test_a_task_that_fails_is_logged_by_its_kind_and_one_that_cancels_its_own_scope_ends(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = FakeClock()
    scope = CancelScope(name="reply-4", clock=clock)

    async def fails() -> None:
        raise LookupError("a made-up failure, never logged")

    async def stops_its_own_scope() -> str:
        await scope.cancel()  # it does not wait on itself
        return "stopped"

    async def call() -> None:
        failing = scope.start(fails(), name="failing")
        await asyncio.sleep(0)
        assert failing.done() and scope.running == 0
        assert await scope.start(stops_its_own_scope(), name="stopper") == "stopped"
        assert scope.cancelled

    caplog.set_level(logging.INFO)
    asyncio.run(call())
    (failed,) = [r for r in caplog.records if r.getMessage() == "scope_task_failed"]
    fields = {"scope": "reply-4", "task": "failing", "failure": "LookupError"}
    assert getattr(failed, "fields", None) == fields
    assert "made-up failure" not in caplog.text
