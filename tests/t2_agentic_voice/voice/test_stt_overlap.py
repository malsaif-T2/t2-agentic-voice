"""An overlap's parts in the speech-to-text bridge (voice/stt_bridge.py, plan 005): the window and
the overlap requests, the turn's transcript reused from the overlap's, at most two requests
an overlap, and the call's end; against the fakes, fed the frames Pipecat's turn processors push,
then through a whole call's pipeline while a reply plays."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.commands import Command, HangUp, HearOverlap, ListenIn, Speak
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    Connected,
    Ending,
    SessionEvent,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import OVERLAP_LEAD_S, TurnSTTBridge

from tests.t2_agentic_voice.fake_session import FakeSession
from tests.t2_agentic_voice.fakes import (
    Captured,
    FakePhrases,
    FakeSpeechToText,
    capturing_output,
)
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    PauseAnalyzer,
    Recorder,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
    voice_calls,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

WINDOW_MS = 750


class Marking(Recorder):
    """A session that, when `mark` is on, marks each turn an overlap as it opens (its
    `HearOverlap`, `WINDOW_MS`), as the session does for a turn over a reply."""

    def __init__(self, stt: TurnSTTBridge, *, mark: bool) -> None:
        super().__init__()
        self.stt, self.mark, self.marked = stt, mark, False

    async def handle(self, event: SessionEvent) -> None:
        await super().handle(event)
        if self.mark and isinstance(event, TurnOpened):
            self.stt.hear_overlap(event.turn_id, WINDOW_MS)
            self.marked = True

    def parts(self, kind: type[Transcribing | Transcribed]) -> list[str]:
        """The parts of the events of `kind` handed so far, in order."""
        return [e.part for e in self.of(kind)]


@dataclass
class Rig:
    session: Marking
    stt: TurnSTTBridge
    worker: PipelineWorker | None = None

    async def feed(self, frames: Sequence[Frame]) -> None:
        assert self.worker is not None
        for frame in frames:
            await self.worker.queue_frame(frame)

    async def turn_done(self) -> None:
        await until(lambda: "turn" in self.session.parts(Transcribed))


def _run(port: FakeSpeechToText, body: Callable[[Rig], Awaitable[None]], *, mark: bool) -> Rig:
    events = EventStream(SYSTEM_CLOCK)
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=port, events=events, report=report, start_s=START_S)
    rig = Rig(Marking(stt, mark=mark), stt)

    async def feed(worker: PipelineWorker) -> None:
        rig.worker = worker
        events.start(rig.session)
        await body(rig)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return rig


def _opening() -> list[Frame]:
    """A turn's opening: 1 s of silence, the detector's start delay of speech, its start and
    the turn's start. The pre-roll then holds 0.6 s, the speech beginning 0.5 s into it."""
    from pipecat.frames.frames import UserStartedSpeakingFrame, VADUserStartedSpeakingFrame

    return [
        *audio_frames(1.0, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
    ]


def _speech(seconds: float, *, stop: bool = True) -> list[Frame]:
    """`seconds` more of speech, then the detector's stop delay of silence and its stop."""
    from pipecat.frames.frames import VADUserStoppedSpeakingFrame

    stopped = [*audio_frames(STOP_S, loud=False), VADUserStoppedSpeakingFrame(stop_secs=STOP_S)]
    return [*audio_frames(seconds), *(stopped if stop else [])]


def _end() -> list[Frame]:
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    return [*audio_frames(0.2, loud=False), UserStoppedSpeakingFrame()]


def test_a_long_overlap_sends_its_window_then_its_overlap_and_its_turn_reuses_the_overlap() -> None:
    """Speech that goes on past the window: the window (750 ms from 300 ms before the speech
    began) while it goes on, the whole overlap at the detector's stop, and the turn's
    transcript the overlap's again, with no third request."""
    port = FakeSpeechToText(["first words", "first words and more"])

    async def body(rig: Rig) -> None:
        await rig.feed(_opening())
        await until(lambda: rig.session.marked)
        await rig.feed([*_speech(1.0), *_end()])
        await rig.turn_done()

    rig = _run(port, body, mark=True)
    session = rig.session
    assert session.parts(Transcribing) == ["window", "overlap"] and len(port.calls) == 2
    assert session.parts(Transcribed) == ["window", "overlap", "turn"]
    (window, _, _), (whole, _, _) = port.calls
    assert window.seconds == pytest.approx(WINDOW_MS / 1000)
    assert whole.seconds == pytest.approx(OVERLAP_LEAD_S + START_S + 1.0 + STOP_S, abs=0.021)
    sent, (_, overlap, turn) = session.of(Transcribing)[1], session.of(Transcribed)
    assert turn.transcript == overlap.transcript and turn.transcript is not None
    assert turn.transcript.text == "first words and more"
    assert (
        (turn.sent_at, turn.audio_s) == (sent.at, sent.audio_s) == (overlap.sent_at, whole.seconds)
    )
    (closed,) = session.of(TurnClosed)
    assert max(overlap.at, closed.at) <= turn.at


def test_a_short_overlap_is_one_request_and_no_window() -> None:
    """Speech that stops before its window is covered: no window, the overlap part at the
    detector's stop, the turn's transcript reused: one request decides it."""
    port = FakeSpeechToText(["short"])

    async def body(rig: Rig) -> None:
        await rig.feed(_opening())
        await until(lambda: rig.session.marked)
        await rig.feed([*_speech(0.1), *_end()])
        await rig.turn_done()

    rig = _run(port, body, mark=True)
    assert rig.session.parts(Transcribing) == ["overlap"] and len(port.calls) == 1
    assert rig.session.parts(Transcribed) == ["overlap", "turn"]


def test_speech_after_the_overlap_part_gets_the_turns_own_request() -> None:
    """The caller speaks again after the overlap part was cut, in the same turn: the turn's
    own request goes, holding all of it, so the overlap and the turn are two requests."""
    from pipecat.frames.frames import VADUserStartedSpeakingFrame

    port = FakeSpeechToText(["first", "first then more"])

    async def body(rig: Rig) -> None:
        await rig.feed(_opening())
        await until(lambda: rig.session.marked)
        await rig.feed(_speech(0.1))
        again = [*audio_frames(START_S), VADUserStartedSpeakingFrame(start_secs=START_S)]
        await rig.feed([*audio_frames(0.2, loud=False), *again, *_speech(0.4), *_end()])
        await rig.turn_done()

    rig = _run(port, body, mark=True)
    assert rig.session.parts(Transcribing) == ["overlap", "turn"] and len(port.calls) == 2
    turn = rig.session.of(Transcribed)[-1]
    assert turn.transcript is not None and turn.transcript.text == "first then more"
    assert port.calls[1][0].seconds > port.calls[0][0].seconds + 0.6


def test_a_mark_that_comes_after_the_detectors_stop_sends_the_overlap_at_once() -> None:
    """io.py's overlaps: a `HearOverlap` that reaches the bridge after the detector heard the
    turn's speech stop gets its overlap part at once, before the turn's end, with no window."""
    port = FakeSpeechToText(["late"])

    async def body(rig: Rig) -> None:
        await rig.feed([*_opening(), *_speech(0.6), *audio_frames(0.1, loud=False)])
        await asyncio.sleep(0.3)  # the frames are taken: the stop has reached the bridge
        rig.stt.hear_overlap(0, WINDOW_MS)
        await until(lambda: bool(rig.session.of(Transcribing)), timeout=1.0)
        assert not rig.session.of(TurnClosed)
        await rig.feed(_end())
        await rig.turn_done()

    rig = _run(port, body, mark=False)
    assert rig.session.parts(Transcribing) == ["overlap"] and len(port.calls) == 1
    assert rig.session.parts(Transcribed) == ["overlap", "turn"]


def test_a_turn_that_closes_with_no_stop_since_its_mark_sends_its_overlap_then() -> None:
    port = FakeSpeechToText(["closed"])

    async def body(rig: Rig) -> None:
        await rig.feed(_opening())
        await until(lambda: rig.session.marked)
        await rig.feed([*_speech(0.1, stop=False), *_end()])
        await rig.turn_done()

    rig = _run(port, body, mark=True)
    assert rig.session.parts(Transcribing) == ["overlap"] and len(port.calls) == 1
    assert rig.session.parts(Transcribed) == ["overlap", "turn"]


def test_a_mark_for_a_turn_already_closed_or_unknown_still_gets_its_overlap_part(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every overlap is decided: a turn closed before its mark came gets its own transcript
    again as its overlap part, and one the bridge no longer knows an empty one, with a line;
    neither sends a request."""
    port = FakeSpeechToText(["closed first"])

    async def body(rig: Rig) -> None:
        await rig.feed([*_opening(), *_speech(0.3), *_end()])
        await rig.turn_done()
        rig.stt.hear_overlap(0, WINDOW_MS)
        rig.stt.hear_overlap(7, WINDOW_MS)
        await until(lambda: len(rig.session.of(Transcribed)) == 3)

    rig = _run(port, body, mark=False)
    turn, overlap, unknown = rig.session.of(Transcribed)
    assert (overlap.part, overlap.turn_id, overlap.transcript) == ("overlap", 0, turn.transcript)
    assert (unknown.part, unknown.turn_id, unknown.transcript, unknown.sent_at) == (
        "overlap",
        7,
        None,
        None,
    )
    assert len(port.calls) == 1 and rig.session.parts(Transcribing) == ["turn"]
    assert "overlap_turn_unknown" in caplog.text


def test_at_the_calls_end_a_part_in_flight_is_cancelled_and_no_part_follows() -> None:
    """io.py's end holds for every part: the window in flight is cancelled (its
    `Transcribing` already handed), no `Transcribed` follows, and a mark after the end sends
    nothing."""
    port = FakeSpeechToText(["never"], delay_s=5.0)

    async def body(rig: Rig) -> None:
        await rig.feed(_opening())
        await until(lambda: rig.session.marked)
        await rig.feed(_speech(0.6, stop=False))
        await until(lambda: bool(rig.session.of(Transcribing)))
        await rig.stt.drop()
        rig.stt.hear_overlap(0, WINDOW_MS)
        await rig.feed(_speech(0.2))
        await asyncio.sleep(0.2)

    rig = _run(port, body, mark=True)
    assert rig.session.parts(Transcribing) == ["window"] and len(port.calls) == 1
    assert not rig.session.of(Transcribed)


def test_in_a_call_an_overlap_over_a_reply_fires_no_pipecat_interruption(
    settings: VoiceSettings,
) -> None:
    """Through a whole call's pipeline: the greeting playing, the caller speaks over it and the
    session marks the turn an overlap. The command reaches the bridge, the window and the
    overlap go, the turn reuses the overlap's transcript, and Pipecat interrupts nothing: the
    greeting plays to its end (plan 005's decision log; D-018, Pipecat's interruptions off)."""
    port = FakeSpeechToText(["over the reply", "over the reply in full"])
    built = voice_calls(settings, stt=port)
    phrases = FakePhrases.of(AGENT)
    phrases.seconds = 4.0
    greeting = AGENT.languages[0].greeting

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, Connected):
            audio = phrases.audio(greeting, language="en")
            hello = Speak(
                reply_id=0, clause=0, turn_id=None, text=greeting, language="en", audio=audio
            )
            return [ListenIn(language="en"), hello]
        if isinstance(event, TurnOpened):
            return [HearOverlap(turn_id=event.turn_id, window_ms=WINDOW_MS)]
        return [HangUp(reason="server")] if isinstance(event, Ending) else []

    captured = Captured()

    async def run() -> FakeSession:
        pipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), PauseAnalyzer()),
            caller=Caller(subject="made-up"),
            consent=Consent(version=None, record_audio=False),
            language=AGENT.languages[0],
            output=capturing_output(captured),
        )
        session = FakeSession(pipeline.setup, pipeline.commands, replies=replies)
        await pipeline.start(session)
        pipeline.connect()
        await until(lambda: bool(captured.audio))
        clip = [*audio_frames(0.3, loud=False), *audio_frames(1.2), *audio_frames(1.0, loud=False)]
        for frame in clip:  # at about real-time pace, as a call's input
            await pipeline.worker.queue_frame(frame)
            await asyncio.sleep(0.02)
        await until(lambda: any(isinstance(e, ClausePlayed) for e in session.events))
        pipeline.leave("server")
        await asyncio.wait_for(pipeline.finished.wait(), timeout=20)
        return session

    session = asyncio.run(asyncio.wait_for(run(), timeout=60))
    parts = [e.part for e in session.events if isinstance(e, Transcribed)]
    assert parts == ["window", "overlap", "turn"]
    steps = [(type(e).__name__, getattr(e, "part", "")) for e in session.events]
    assert steps.index(("Transcribing", "overlap")) < steps.index(("TurnClosed", ""))
    assert len(port.calls) == 2 and captured.interruptions == []
    assert captured.audio_s() == pytest.approx(4.0, abs=0.05)
