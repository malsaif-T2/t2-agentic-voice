"""One call's pipeline from its start to its end (voice/pipeline.py): each step of the end bounded,
so no call's end hangs on its session, its runner or a pipeline that never started."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.voice import pipeline as pipeline_module
from t2_agentic_voice.voice.pipeline import CallPipeline
from t2_agentic_voice.voice.session.session_events import Ending

from tests.t2_agentic_voice.fakes import Captured, capturing_output
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import Recorder, ToneVAD, voice_calls


def _end(
    settings: VoiceSettings, step: Callable[[CallPipeline, Recorder], Awaitable[None]]
) -> Recorder:
    """Build a call's pipeline with a session that never hangs up, run `step`, then end the
    call from outside and wait for its end."""
    built = voice_calls(settings)
    session = Recorder()

    async def run() -> None:
        pipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), None),
            caller=Caller(subject="made-up"),
            consent=Consent(version=None, record_audio=False),
            language=AGENT.languages[0],
            output=capturing_output(Captured()),
        )
        await step(pipeline, session)
        pipeline.leave("server")
        pipeline.leave("server")  # once ended, a second end does nothing
        pipeline.fail("media")
        await asyncio.wait_for(pipeline.finished.wait(), timeout=20)

    asyncio.run(run())
    return session


def test_a_session_that_does_not_hang_up_is_ended_all_the_same(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(pipeline_module, "HANGUP_WAIT_S", 0.1)

    async def start(pipeline: CallPipeline, session: Recorder) -> None:
        await pipeline.start(session)

    session = _end(settings, start)
    assert [e.reason for e in session.of(Ending)] == ["server"] and session.closed
    assert "session_did_not_hang_up" in caplog.text


def test_a_pipeline_that_never_started_ends_at_once(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline_module, "HANGUP_WAIT_S", 0.0)

    async def nothing(pipeline: CallPipeline, session: Recorder) -> None:
        return None

    assert _end(settings, nothing).events == []


def test_a_runner_that_hangs_or_fails_at_the_end_is_given_up(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The runner's end is bounded by `CLOSE_TIMEOUT_S`, and its own failure is logged by type:
    either way the call ends."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(pipeline_module, "HANGUP_WAIT_S", 0.0)
    monkeypatch.setattr(pipeline_module, "CLOSE_TIMEOUT_S", 0.1)

    async def fails() -> None:
        raise RuntimeError("the runner's own text")

    async def hangs() -> None:
        await asyncio.sleep(10)

    for odd in (hangs, fails):

        async def swap(
            pipeline: CallPipeline,
            session: Recorder,
            odd: Callable[[], Coroutine[Any, Any, None]] = odd,
        ) -> None:
            await pipeline.start(session)
            await pipeline.worker.cancel()  # the real runner ends; a stand-in takes its place
            pipeline._run = asyncio.create_task(odd())

        _end(settings, swap)
    lines = [r.getMessage() for r in caplog.records]
    assert "pipeline_cancel_timeout" in lines and "pipeline_failed" in lines
    assert "own text" not in caplog.text
