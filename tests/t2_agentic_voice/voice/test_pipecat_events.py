"""Pipecat's failures as the library's (voice/pipecat_events.py): each error frame a log line that
holds no call content, a speech bridge's a `ProviderFailed`, a transport's that leaves it unable
to work the end of the call; and, through a whole call, a `TransportFailed` with the session's
`TransportFailure`."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event, ProviderFailed, TransportFailed, TransportStage
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.commands import HangUp
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Connected, TransportFailure
from t2_agentic_voice.voice.session_bridge import CallEvents
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.tts_bridge import ClauseTTSBridge

from tests.t2_agentic_voice.fakes import (
    Captured,
    FakeClock,
    FakeSpeechToText,
    FakeTextToSpeech,
    capturing_output,
)
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import Tail, ToneVAD, voice_calls

SECRET = "the caller said a private phrase"


def test_an_error_frame_is_a_line_with_no_content_and_a_speech_bridges_a_provider_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from pipecat.frames.frames import ErrorFrame
    from pipecat.utils.errors import ErrorCategory

    emitted: list[Event] = []
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=FakeClock())
    events = CallEvents(SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=FakeSpeechToText(), events=events, report=report, start_s=0.2)
    tts = ClauseTTSBridge(tts=FakeTextToSpeech(), events=events, report=report, timeout_s=6.0)
    output = capturing_output(Captured())
    speech = [(stt, "speech_to_text"), (tts, "text_to_speech")]

    async def run() -> list[TransportStage | None]:
        stages = [report.error_frame(ErrorFrame(error=SECRET, processor=output), speech=speech)]
        await output.set_usable(False)
        unusable = ErrorFrame(error=SECRET, processor=output, exception=TimeoutError(SECRET))
        stages.append(report.error_frame(unusable, speech=speech))
        limited = ProviderError("timeout", True)
        stages.append(
            report.error_frame(
                ErrorFrame(error=SECRET, processor=stt, exception=limited), speech=speech
            )
        )
        crashed = ErrorFrame(
            error=SECRET,
            processor=tts,
            exception=ValueError(SECRET),
            category=ErrorCategory.UNKNOWN,
        )
        stages.append(report.error_frame(crashed, speech=speech))
        stages.append(report.error_frame(ErrorFrame(error=SECRET), speech=speech))
        stages.append(report.error_frame(ErrorFrame(error=SECRET, processor=Tail()), speech=speech))
        return stages

    assert asyncio.run(run()) == [None, "media", None, None, None, None]
    failed = [(e.kind, e.retryable) for e in emitted if isinstance(e, ProviderFailed)]
    assert failed == [("timeout", True), ("server_error", False)] and len(emitted) == 2
    lines = [r for r in caplog.records if r.getMessage() == "pipecat_error"]
    assert len(lines) == 6 and SECRET not in caplog.text
    assert getattr(lines[1], FIELDS)["usable"] is False


def test_a_transport_that_cannot_write_ends_the_call_as_a_failure(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """Through a whole call: the output transport pushes an error that leaves it unable to work
    (as Pipecat's does when a write never returns); the call's `TransportFailed` is emitted,
    the session is handed its `TransportFailure` at `media` and hangs up, and the call ends."""
    caplog.set_level(logging.INFO)
    built = voice_calls(settings)
    captured = Captured()
    output = capturing_output(captured)

    async def run() -> None:
        await built.calls.start()
        pipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), None),
            caller=Caller(subject="made-up"),
            consent=Consent(version=None, record_audio=False),
            language=AGENT.languages[0],
            output=output,
            record=True,
        )
        await pipeline.start(built.calls._session(pipeline))
        pipeline.connect()
        await output.push_error(SECRET, force_treat_as_permanent=True)
        await asyncio.wait_for(pipeline.finished.wait(), timeout=20)
        handed = pipeline.events.handed or []
        assert isinstance(handed[0], Connected)
        assert [e.stage for e in handed if isinstance(e, TransportFailure)] == ["media"]
        assert [c for _, c in pipeline.commands.given or [] if isinstance(c, HangUp)] == [
            HangUp(reason="transport")
        ]

    asyncio.run(run())
    assert [e.stage for e in built.emitted if isinstance(e, TransportFailed)] == ["media"]
    assert SECRET not in caplog.text


def test_a_report_stamps_its_events_on_the_calls_clock(tmp_path: Path) -> None:
    clock = FakeClock()
    emitted: list[Event] = []
    FailureReport(call_id="call-1", emit=emitted.append, clock=clock).transport_failed("connect")
    (failed,) = emitted
    assert isinstance(failed, TransportFailed) and failed.at == clock.wall()
