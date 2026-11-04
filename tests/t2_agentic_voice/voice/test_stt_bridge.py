"""The speech-to-text bridge (voice/stt_bridge.py): one request per user turn, against the fakes,
fed the turn frames Pipecat's turn processors push, or a clip through the whole file-fed
pipeline."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.voice import stt_bridge as bridge_module
from t2_agentic_voice.voice.file_transport import feed_file
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import CallEvents
from t2_agentic_voice.voice.stt_bridge import PREROLL_PAD_S, TRAIL_S, TurnSTTBridge

from tests.t2_agentic_voice.fakes import FakeSpeechToText, tone
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    Recorder,
    audio_frames,
    run_pipeline,
    until,
    voice_calls,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)


@dataclass
class Rig:
    events: CallEvents
    session: Recorder
    stt: TurnSTTBridge
    emitted: list[Event]


def _run(port: FakeSpeechToText, body: Callable[[Rig, PipelineWorker], Awaitable[None]]) -> Rig:
    events, session, emitted = CallEvents(SYSTEM_CLOCK), Recorder(), list[Event]()
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=port, events=events, report=report, start_s=START_S)
    rig = Rig(events, session, stt, emitted)

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        await body(rig, worker)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return rig


async def _turn(worker: PipelineWorker, *, speech_s: float = 0.4, after_s: float = 0.1) -> None:
    """One turn's frames as Pipecat's turn processors push them: the pre-roll's silence, the
    detector's start, the turn's start, its speech, the detector's stop, then the turn's end
    `after_s` later."""
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )

    frames: list[Frame] = [
        *audio_frames(1.0, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
        *audio_frames(speech_s),
        *audio_frames(STOP_S, loud=False),
        VADUserStoppedSpeakingFrame(stop_secs=STOP_S),
        *audio_frames(after_s + 1.0, loud=False),
    ]
    for frame in frames:
        await worker.queue_frame(frame)
    await asyncio.sleep(after_s)
    await worker.queue_frame(UserStoppedSpeakingFrame())


def test_a_turn_is_one_request_of_its_held_audio_trimmed_after_its_last_stop() -> None:
    """The request holds the pre-roll (the detector's start delay and `PREROLL_PAD_S`), the
    turn's speech, and `TRAIL_S` after the detector's stop, whatever came later; the turn is
    opened, closed and transcribed once, in the language last named, with the times read as
    each frame came."""
    port = FakeSpeechToText(["heard"])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        rig.stt.listen_in("ar")
        await _turn(worker)
        await until(lambda: bool(rig.session.of(Transcribed)))

    rig = _run(port, body)
    ((clip, language, prompt),) = port.calls
    expected = START_S + PREROLL_PAD_S + 0.4 + STOP_S + TRAIL_S
    assert clip.seconds == pytest.approx(expected, abs=0.021) and (language, prompt) == ("ar", None)
    (opened,) = rig.session.of(TurnOpened)
    (closed,) = rig.session.of(TurnClosed)
    (sent,) = rig.session.of(Transcribing)
    (heard,) = rig.session.of(Transcribed)
    assert opened.turn_id == closed.turn_id == sent.turn_id == heard.turn_id == 0
    assert opened.speech_at <= opened.at <= closed.speech_ended_at <= closed.at <= sent.at
    assert closed.at - closed.speech_ended_at >= 0.05
    assert heard.sent_at == sent.at and heard.audio_s == sent.audio_s == clip.seconds
    assert heard.transcript is not None and heard.transcript.text == "heard"


def test_a_turn_that_closes_with_no_stop_of_the_detectors_sends_all_it_held() -> None:
    """With no stop of the detector's in the turn, nothing trims its request: it holds the
    pre-roll and all the speech held."""
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
    )

    port = FakeSpeechToText(["all of it"])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        frames: list[Frame] = [
            *audio_frames(1.0, loud=False),
            *audio_frames(START_S),
            VADUserStartedSpeakingFrame(start_secs=START_S),
            UserStartedSpeakingFrame(),
            *audio_frames(0.4),
            UserStoppedSpeakingFrame(),
        ]
        for frame in frames:
            await worker.queue_frame(frame)
        await until(lambda: bool(rig.session.of(Transcribed)))

    _run(port, body)
    ((clip, _, _),) = port.calls
    assert clip.seconds == pytest.approx(START_S + PREROLL_PAD_S + 0.4, abs=0.021)


def test_the_next_turn_can_open_before_the_last_ones_transcript() -> None:
    """The request runs on a task of its own: turn 1 opens while turn 0's is in flight, each
    keyed on its turn."""
    port = FakeSpeechToText(["first", "second"], delay_s=0.5)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _turn(worker, after_s=0.05)
        await _turn(worker, after_s=0.05)
        await until(lambda: len(rig.session.of(Transcribed)) == 2)

    rig = _run(port, body)
    turns = (TurnOpened, TurnClosed, Transcribing, Transcribed)
    order = [(type(e).__name__, e.turn_id) for e in rig.session.events if isinstance(e, turns)]
    assert order.index(("TurnOpened", 1)) < order.index(("Transcribed", 0))
    assert [e.transcript.text for e in rig.session.of(Transcribed) if e.transcript] == [
        "first",
        "second",
    ]


def test_each_turn_gets_exactly_one_result_when_its_request_fails_or_none_goes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `ProviderError` is the turn's failed `Transcribed` and a `provider_failed` line naming
    it, with no public event, which the session emits from the `Transcribed`; an adapter's own
    exception fails it as `server_error`, logged by type alone; a muted bridge holds no audio
    and an unusable one sends nothing, each turn's `Transcribed` then naming no request."""

    class Odd(FakeSpeechToText):
        async def transcribe(
            self, clip: AudioClip, *, language: str | None, prompt: str | None
        ) -> Transcript:
            if len(self.calls) == 1:
                self.calls.append((clip, language, prompt))
                raise ValueError("the adapter's own text")
            return await super().transcribe(clip, language=language, prompt=prompt)

    port = Odd([ProviderError("timeout", True)])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        from pipecat.frames.frames import STTMuteFrame

        await _turn(worker)
        await until(lambda: len(rig.session.of(Transcribed)) == 1)
        await _turn(worker)
        await until(lambda: len(rig.session.of(Transcribed)) == 2)
        await worker.queue_frame(STTMuteFrame(mute=True))
        await _turn(worker)
        await until(lambda: len(rig.session.of(Transcribed)) == 3)
        await worker.queue_frame(STTMuteFrame(mute=False))
        await rig.stt.set_usable(False)
        await _turn(worker)
        await until(lambda: len(rig.session.of(Transcribed)) == 4)

    rig = _run(port, body)
    results = [(e.failure, e.retryable, e.sent_at is None) for e in rig.session.of(Transcribed)]
    assert results == [
        ("timeout", True, False),
        ("server_error", False, False),
        (None, False, True),
        (None, False, True),
    ]
    assert len(port.calls) == 2 and len(rig.session.of(Transcribing)) == 2
    lines = [getattr(r, FIELDS) for r in caplog.records if r.getMessage() == "provider_failed"]
    assert [(line["kind"], line["turn_id"]) for line in lines] == [
        ("timeout", 0),
        ("server_error", 1),
    ]
    assert rig.emitted == []
    assert "stt_request_failed" in caplog.text and "own text" not in caplog.text


def test_a_long_turn_keeps_its_first_audio_and_says_so_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(bridge_module, "MAX_TURN_S", 1.0)
    port = FakeSpeechToText(["long"])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _turn(worker, speech_s=1.0)
        await until(lambda: bool(rig.session.of(Transcribed)))

    rig = _run(port, body)
    assert port.calls[0][0].seconds <= 1.0 and rig.session.of(Transcribed)
    assert [r.getMessage() for r in caplog.records].count("turn_audio_capped") == 1


def test_at_the_calls_end_the_held_audio_is_dropped_and_a_request_cancelled() -> None:
    """io.py's end: a request in flight is cancelled (its `Transcribing` already handed, so it
    counts), no `Transcribed` follows, and later frames are left alone."""
    port = FakeSpeechToText(["never"], delay_s=5.0)

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _turn(worker)
        await until(lambda: bool(rig.session.of(Transcribing)))
        await rig.stt.drop()
        await _turn(worker)
        await asyncio.sleep(0.2)

    rig = _run(port, body)
    assert len(port.calls) == 1 and len(rig.session.of(Transcribing)) == 1
    assert not rig.session.of(Transcribed) and len(rig.session.of(TurnOpened)) == 1


def test_the_bridge_sends_no_request_for_a_frame_and_times_no_stream() -> None:
    events = CallEvents(SYSTEM_CLOCK)
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=FakeSpeechToText(), events=events, report=report, start_s=0.2)

    async def frames() -> list[object]:
        return [frame async for frame in stt.run_stt(b"\x00\x00")]

    assert asyncio.run(frames()) == [None] and stt.supports_ttfs is False


def test_a_turn_with_a_pause_in_it_is_one_request(tmp_path: Path) -> None:
    """Through the whole file-fed pipeline, with a turn analyzer that calls the first pause
    unfinished: speech, a pause past the detector's stop, more speech, then the turn's end; the
    speech-to-text bridge sends Whisper one request holding both parts and the pause."""
    settings = VoiceSettings(env="test", storage=StorageSettings(var_dir=tmp_path / "var"))
    built = voice_calls(settings, stt=FakeSpeechToText(["one turn"]), incomplete=1)
    pause = bytes(round(0.6 * 16_000) * 2)
    clip = AudioClip(pcm16=tone(0.6, 16_000) + pause + tone(0.6, 16_000))

    async def run() -> None:
        await built.calls.start()
        try:
            fed = await feed_file(
                built.calls,
                clip,
                call_id="call-1",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=0.4,
                tail_s=1.0,
            )
        finally:
            await built.calls.aclose()
        assert len([e for e in fed.events if isinstance(e, TurnOpened)]) == 1
        assert len([e for e in fed.events if isinstance(e, Transcribing)]) == 1

    asyncio.run(asyncio.wait_for(run(), timeout=60))
    ((sent, _, _),) = built.stt.calls
    assert sent.seconds >= 0.6 + 0.6 + 0.6
    warmed, call = built.analyzers  # the one `start` warmed, then the call's own
    assert [s.name for s in call.decided] == ["INCOMPLETE", "COMPLETE"] and not warmed.decided


def test_a_turn_no_analyzer_ends_is_ended_by_the_silence_fallback_and_billed_none_of_it(
    tmp_path: Path,
) -> None:
    """`turns.max_silence_ms` ends a turn the analyzer leaves open; the request still ends
    `TRAIL_S` after the detector's last stop, so the fallback's silence is not sent."""
    turns = TurnSettings(max_silence_ms=1000)
    settings = VoiceSettings(
        env="test", turns=turns, storage=StorageSettings(var_dir=tmp_path / "var")
    )
    built = voice_calls(settings, stt=FakeSpeechToText(["late"]), incomplete=1)

    async def run() -> None:
        await built.calls.start()
        try:
            fed = await feed_file(
                built.calls,
                AudioClip(pcm16=tone(0.6, 16_000)),
                call_id="call-1",
                caller=CALLER,
                consent=CONSENT,
                language=AGENT.languages[0],
                lead_s=0.4,
                tail_s=2.0,
            )
        finally:
            await built.calls.aclose()
        (closed,) = [e for e in fed.events if isinstance(e, TurnClosed)]
        assert closed.at - closed.speech_ended_at >= 0.7

    asyncio.run(asyncio.wait_for(run(), timeout=60))
    ((sent, _, _),) = built.stt.calls
    assert sent.seconds <= START_S + PREROLL_PAD_S + 0.6 + STOP_S + TRAIL_S + 0.1


def test_logging_the_bridge_holds_no_heard_words(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    port = FakeSpeechToText(["a private phrase"])

    async def body(rig: Rig, worker: PipelineWorker) -> None:
        await _turn(worker)
        await until(lambda: bool(rig.session.of(Transcribed)))

    _run(port, body)
    assert "private" not in caplog.text
