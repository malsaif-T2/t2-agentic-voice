"""The hold's signals for the early start (voice/turn_hold.py, stt_bridge.py; plan 006, Q2): the
real turn processors push a `TurnHeldFrame` behind the detector's stop when Smart Turn calls a
pause complete, and a `HoldResumedFrame` behind the detector's start when speech drops the hold;
the speech-to-text bridge, with the early start on, hands `TurnHeld` and sends the turn's speech
so far as its `held` request, which the turn's own transcript reuses when no speech followed,
and on a resume cancels it and hands `HoldResumed`, the turn's own request then holding it all;
with the early start off it does as it did."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    HoldResumed,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnHeld,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import CallEvents
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.turn_hold import HeldTurnStop, HoldResumedFrame, TurnHeldFrame
from t2_agentic_voice.voice.turns import turn_processors

from tests.t2_agentic_voice.fakes import FakeSpeechToText
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    PauseAnalyzer,
    Recorder,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker


def _kinds(tail: Tail) -> list[str]:
    names = {
        "VADUserStartedSpeakingFrame",
        "VADUserStoppedSpeakingFrame",
        "UserStoppedSpeakingFrame",
        "TurnHeldFrame",
        "HoldResumedFrame",
    }
    return [type(f).__name__ for f, _ in tail.frames if type(f).__name__ in names]


def _through_the_turn_processors(speech: list[tuple[float, float]]) -> list[str]:
    """The frames the real turn processors push for `speech`'s (tone, silence) pairs, a pause
    Smart Turn calls complete held 600 ms (the stand-in analyzer calls every pause so)."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    vad, user_turns = turn_processors(
        ToneVAD(), PauseAnalyzer(), TurnSettings(complete_hold_ms=600)
    )
    tail = Tail()

    async def feed(worker: PipelineWorker) -> None:
        for frame in audio_frames(0.2, loud=False):
            await worker.queue_frame(frame)
        for tone_s, silence_s in speech:
            for frame in [*audio_frames(tone_s), *audio_frames(silence_s, loud=False)]:
                await worker.queue_frame(frame)
        await until(lambda: bool(tail.of(UserStoppedSpeakingFrame)))
        await asyncio.sleep(0.05)

    asyncio.run(run_pipeline([vad, user_turns, tail], feed))
    return _kinds(tail)


def test_the_hold_is_signalled_behind_the_detectors_stop_before_the_turns_end() -> None:
    assert _through_the_turn_processors([(0.4, 0.8)]) == [
        "VADUserStartedSpeakingFrame",
        "VADUserStoppedSpeakingFrame",
        "TurnHeldFrame",
        "UserStoppedSpeakingFrame",
    ]


def test_speech_resumed_in_the_hold_is_signalled_behind_the_detectors_start() -> None:
    assert _through_the_turn_processors([(0.4, 0.3), (0.4, 0.8)]) == [
        "VADUserStartedSpeakingFrame",
        "VADUserStoppedSpeakingFrame",
        "TurnHeldFrame",
        "VADUserStartedSpeakingFrame",
        "HoldResumedFrame",
        "VADUserStoppedSpeakingFrame",
        "TurnHeldFrame",
        "UserStoppedSpeakingFrame",
    ]


def test_the_strategy_pushes_each_signal_as_a_frame_of_its_own() -> None:
    stop = HeldTurnStop(hold_s=0.6, turn_analyzer=PauseAnalyzer(), wait_for_transcript=False)
    pushed: list[object] = []

    async def push(_: object, frame: object, direction: object) -> None:
        pushed.append(frame)

    stop.add_event_handler("on_push_frame", push)

    async def signals() -> None:
        await stop.hold_began()
        await stop.hold_resumed()

    asyncio.run(signals())
    assert [type(frame) for frame in pushed] == [TurnHeldFrame, HoldResumedFrame]
    assert not stop.decision_scheduled


def _bridge(port: FakeSpeechToText, frames: list[Frame], *, early: bool) -> Recorder:
    """The bridge, with the early start on or off, fed `frames`, then the turn's end."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    events, session, emitted = CallEvents(SYSTEM_CLOCK), Recorder(), list[Event]()
    report = FailureReport(call_id="call-1", emit=emitted.append, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(stt=port, events=events, report=report, start_s=START_S, early=early)

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        for frame in frames:
            await worker.queue_frame(frame)
        await asyncio.sleep(0.1)
        await worker.queue_frame(UserStoppedSpeakingFrame())
        await until(lambda: bool(session.of(Transcribed)) and len(port.calls) >= 1)
        await asyncio.sleep(0.1)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return session


def _speech(*, resumed: bool) -> list[Frame]:
    """A turn's frames as the turn processors push them, its hold signalled after its stop, and
    with `resumed` speech that drops the hold, then its own stop and hold."""
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )

    frames: list[Frame] = [
        *audio_frames(1.0, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
        *audio_frames(0.4),
        *audio_frames(STOP_S, loud=False),
        VADUserStoppedSpeakingFrame(stop_secs=STOP_S),
        TurnHeldFrame(),
        *audio_frames(0.2, loud=False),
    ]
    if resumed:
        frames += [
            *audio_frames(START_S),
            VADUserStartedSpeakingFrame(start_secs=START_S),
            HoldResumedFrame(),
            *audio_frames(0.6),
            *audio_frames(STOP_S, loud=False),
            VADUserStoppedSpeakingFrame(stop_secs=STOP_S),
            TurnHeldFrame(),
        ]
    return frames


def test_the_bridge_sends_the_held_request_at_once_and_the_turn_reuses_it() -> None:
    port = FakeSpeechToText(["I want to reset my password"])
    session = _bridge(port, _speech(resumed=False), early=True)
    kinds = [type(e).__name__ for e in session.events]
    assert kinds == [
        "TurnOpened",
        "TurnHeld",
        "Transcribing",
        "Transcribed",
        "TurnClosed",
        "Transcribed",
    ]
    held, own = session.of(Transcribed)
    assert (session.of(Transcribing)[0].part, held.part, own.part) == ("held", "held", "turn")
    assert own.transcript == held.transcript and len(port.calls) == 1  # one request
    assert isinstance(session.events[0], TurnOpened) and isinstance(session.events[4], TurnClosed)


def test_speech_resumed_in_the_hold_cancels_the_held_request_and_the_turn_asks_again() -> None:
    port = FakeSpeechToText(["I want to reset", "", "I want to reset my password"], delay_s=0.3)
    session = _bridge(port, _speech(resumed=True), early=True)
    resumed = session.of(HoldResumed)
    assert len(session.of(TurnHeld)) == 2 and len(resumed) == 1
    after = session.events[session.events.index(resumed[0]) :]
    assert not any(isinstance(e, Transcribed) and e.part == "held" for e in after[:2])
    (own,) = [e for e in session.of(Transcribed) if e.part == "turn"]
    first_held = session.of(Transcribing)[0]
    assert own.audio_s > first_held.audio_s  # the whole turn, joined


def test_with_the_early_start_off_the_bridge_ignores_the_hold() -> None:
    port = FakeSpeechToText(["I want to reset my password"])
    session = _bridge(port, _speech(resumed=False), early=False)
    assert [type(e).__name__ for e in session.events] == [
        "TurnOpened",
        "TurnClosed",
        "Transcribing",
        "Transcribed",
    ]
