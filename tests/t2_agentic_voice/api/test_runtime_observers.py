"""The runtime's observers (api/runtime.py, "Observers"; the design's 6.6): each event voice emits
goes, queued off the call's path, to each observer of its kind; one that raises or runs over is
logged by its type, never the event, and the next one runs; a full queue drops and logs; and the
events still queued at the stop are handed on, within a bound."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from t2_agentic_voice.api import runtime
from t2_agentic_voice.core.events import CallEnded, CallReport, CallStarted, Event, UserTurnEnded

from tests.t2_agentic_voice.api.runtime_support import Harness, dev_settings, serving

pytestmark = pytest.mark.usefixtures("patched_stores")

AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
HEARD = "zx-made-up-heard-words"


REPORT = CallReport(call_id="c-1", agent="echo", started_at=AT, ended_at=AT, ended_by="hangup")


def _emit(harness: Harness, *events: Event) -> None:
    emit = harness.built[0]["emit"]
    for event in events:
        emit(event)


def test_each_event_goes_to_each_observer_of_its_kind(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(dev_settings(tmp_path))
    seen: list[tuple[str, str]] = []

    @harness.runtime.on(Event)
    async def every(event: Event) -> None:
        seen.append(("every", type(event).__name__))

    @harness.runtime.on(UserTurnEnded)
    async def failing(event: UserTurnEnded) -> None:
        raise ValueError(event.heard)

    @harness.runtime.on(UserTurnEnded)
    async def heard(event: UserTurnEnded) -> None:
        seen.append(("heard", event.heard))

    async def scene() -> None:
        async with serving(harness.app()):
            _emit(
                harness,
                CallStarted(call_id="c-1", at=AT),
                UserTurnEnded(call_id="c-1", turn_id=0, at=AT, heard=HEARD),
            )
            await asyncio.sleep(0.05)

    asyncio.run(scene())
    assert seen == [("every", "CallStarted"), ("every", "UserTurnEnded"), ("heard", HEARD)]
    failed = [r for r in caplog.records if r.getMessage() == "observer_failed"]
    assert len(failed) == 1 and failed[0].levelno == logging.WARNING
    assert HEARD not in caplog.text


def test_an_observer_that_runs_over_is_cut_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(runtime, "OBSERVER_TIMEOUT_S", 0.05)
    harness = Harness(dev_settings(tmp_path))
    after: list[str] = []

    @harness.runtime.on(CallStarted)
    async def slow(event: CallStarted) -> None:
        await asyncio.sleep(10)

    @harness.runtime.on(CallStarted)
    async def next_one(event: CallStarted) -> None:
        after.append(event.call_id)

    async def scene() -> None:
        async with serving(harness.app()):
            _emit(harness, CallStarted(call_id="c-1", at=AT))
            await asyncio.sleep(0.2)

    asyncio.run(scene())
    assert after == ["c-1"]
    assert [r.getMessage() for r in caplog.records].count("observer_timed_out") == 1


def test_an_event_no_observer_takes_is_not_queued_and_a_full_queue_drops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(runtime, "OBSERVER_QUEUE", 1)
    harness = Harness(dev_settings(tmp_path))
    ended: list[str] = []

    @harness.runtime.on(CallEnded)
    async def observer(event: CallEnded) -> None:
        ended.append(event.call_id)

    async def scene() -> None:
        async with serving(harness.app()):
            _emit(harness, CallStarted(call_id="c-0", at=AT))  # no observer of its kind
            _emit(harness, *(CallEnded(call_id=f"c-{n}", at=AT, report=REPORT) for n in (1, 2)))

    asyncio.run(scene())
    assert ended == ["c-1"]  # handed on at the stop; the second dropped
    assert [r.getMessage() for r in caplog.records].count("observer_queue_full") == 1


def test_the_events_still_queued_at_the_stop_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(runtime, "OBSERVER_TIMEOUT_S", 0.05)
    harness = Harness(dev_settings(tmp_path))
    gate = asyncio.Event()

    @harness.runtime.on(CallStarted)
    async def stuck(event: CallStarted) -> None:
        await gate.wait()

    async def scene() -> None:
        async with serving(harness.app()):
            _emit(harness, *(CallStarted(call_id=f"c-{n}", at=AT) for n in range(3)))

    asyncio.run(scene())
    assert "observers_not_drained" in [r.getMessage() for r in caplog.records]
