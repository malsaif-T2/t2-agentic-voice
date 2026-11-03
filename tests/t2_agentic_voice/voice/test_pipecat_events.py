"""Pipecat's failures as the library's (voice/pipecat_events.py): each error frame a log line that
holds no call content, a speech bridge's a `ProviderFailed`, a transport's that leaves it unable
to work the end of the call; and, through a whole call with the real session (`CallSession`),
each failure exactly one public event: a turn's, a clause's, a speech bridge's error frame and
the connection's. The session emits the events of what it is handed, the report only the error
frame's."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event, ProviderFailed, TransportFailed, TransportStage
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.file_transport import feed_file
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import HangUp
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    Connected,
    Transcribed,
    TransportFailure,
)
from t2_agentic_voice.voice.session_bridge import CallEvents
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.tts_bridge import ClauseTTSBridge

from tests.t2_agentic_voice.fakes import (
    Captured,
    FakeClock,
    FakeSpeechToText,
    FakeTextToSpeech,
    capturing_output,
    tone,
)
from tests.t2_agentic_voice.session_fakes import AGENT, FakePhrases
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, Tail, ToneVAD, voice_calls

SECRET = "the caller said a private phrase"
CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
LIMITED = ProviderError("rate_limited", True)


def _failures(emitted: list[Event]) -> list[ProviderFailed | TransportFailed]:
    return [e for e in emitted if isinstance(e, ProviderFailed | TransportFailed)]


async def _until_failed(emitted: list[Event]) -> None:
    while not _failures(emitted):
        await asyncio.sleep(0.01)


class _Refusing(FakeTextToSpeech):
    """The fakes' text-to-speech, refusing every request before any audio."""

    def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.failures[text] = LIMITED
        return super().synthesize(text, language=language)


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


def test_a_transport_that_cannot_write_ends_the_call_as_one_failure(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    """Through a whole call with the real session: the output transport pushes an error that
    leaves it unable to work (as Pipecat's does when a write never returns); the session is
    handed its `TransportFailure` at `media`, emits the call's one `TransportFailed` and hangs
    up, and the call ends; the report logs the failure and emits nothing."""
    caplog.set_level(logging.INFO)
    built = voice_calls(settings)
    captured = Captured()
    output = capturing_output(captured)

    async def run() -> None:
        await built.calls.start()
        pipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), None),
            caller=CALLER,
            consent=CONSENT,
            language=AGENT.languages[0],
            output=output,
            record=True,
        )
        await pipeline.start(CallSession(pipeline.setup, pipeline.commands))
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
    (failed,) = _failures(built.emitted)
    assert isinstance(failed, TransportFailed) and failed.stage == "media"
    assert [r.getMessage() for r in caplog.records].count("transport_failed") == 1
    assert SECRET not in caplog.text


def test_a_speech_bridges_error_frame_is_one_provider_failure_in_a_whole_call(
    settings: VoiceSettings,
) -> None:
    """Through a whole call with the real session: the text-to-speech bridge pushes an error
    frame, of which the session is handed no event; the report emits its one `ProviderFailed`,
    naming no turn."""
    built = voice_calls(settings)

    async def run() -> None:
        await built.calls.start()
        pipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), None),
            caller=CALLER,
            consent=CONSENT,
            language=AGENT.languages[0],
            output=capturing_output(Captured()),
            record=True,
        )
        await pipeline.start(CallSession(pipeline.setup, pipeline.commands))
        pipeline.connect()
        await pipeline.tts_bridge.push_error(SECRET, exception=LIMITED)
        await asyncio.wait_for(_until_failed(built.emitted), timeout=20)
        pipeline.leave("caller_left")
        await asyncio.wait_for(pipeline.finished.wait(), timeout=20)

    asyncio.run(run())
    (failed,) = _failures(built.emitted)
    assert isinstance(failed, ProviderFailed)
    assert (failed.kind, failed.retryable, failed.turn_id) == ("rate_limited", True, None)


@pytest.mark.parametrize("failing", ["speech_to_text", "text_to_speech"])
def test_a_turn_or_a_clause_that_fails_is_one_provider_failure_in_a_whole_call(
    settings: VoiceSettings, failing: str
) -> None:
    """A file-fed call with the real session: the turn's request fails (its failed
    `Transcribed`), or the echo's (its `ClauseFailed`); the session emits the one
    `ProviderFailed`, naming the turn, and the report only logs it."""
    stt = FakeSpeechToText([LIMITED if failing == "speech_to_text" else "hello there"])
    tts = _Refusing() if failing == "text_to_speech" else FakeTextToSpeech()
    emitted: list[Event] = []
    calls = VoiceCalls(
        agent=AGENT,
        settings=settings,
        stt=stt,
        tts=tts,
        phrases=FakePhrases.of(AGENT),
        tracing=Tracing(),
        emit=emitted.append,
        speech_detector=ToneVAD,
        turn_analyzer=PauseAnalyzer,
    )

    async def run() -> None:
        await calls.start()
        try:
            fed = await feed_file(
                calls,
                AudioClip(pcm16=tone(0.8, 16_000)),
                call_id="call-1",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=0.4,
                tail_s=1.5,
            )
        finally:
            await calls.aclose()
        (transcribed,) = [e for e in fed.events if isinstance(e, Transcribed)]
        clauses = [e for e in fed.events if isinstance(e, ClauseFailed)]
        if failing == "speech_to_text":
            assert transcribed.failure == "rate_limited" and not clauses
        else:
            assert transcribed.failure is None and len(clauses) == 1

    asyncio.run(asyncio.wait_for(run(), timeout=60))
    (failed,) = _failures(emitted)
    assert isinstance(failed, ProviderFailed)
    assert (failed.kind, failed.retryable, failed.turn_id) == ("rate_limited", True, 0)


def test_a_report_logs_what_the_session_hears_of_and_stamps_its_own_event_on_the_clock() -> None:
    """A port's failure and the connection's are lines alone, since the session emits their
    events; a speech bridge's error frame's `ProviderFailed` is stamped on the call's clock."""
    from pipecat.frames.frames import ErrorFrame

    clock = FakeClock()
    emitted: list[Event] = []
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=clock)
    report.provider_failed("speech_to_text", "timeout", True, turn_id=0)
    report.transport_failed("connect")
    assert emitted == []
    events = CallEvents(SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=FakeSpeechToText(), events=events, report=report, start_s=0.2)
    frame = ErrorFrame(error=SECRET, processor=stt, exception=LIMITED)
    assert report.error_frame(frame, speech=[(stt, "speech_to_text")]) is None
    (failed,) = emitted
    assert isinstance(failed, ProviderFailed) and failed.at == clock.wall()
