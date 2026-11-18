"""What the tests of a call heard over its stream share (voice/stt_stream.py, stt_streamed.py;
plan 010's 5.1): the bridge of a talker call on ElevenLabs' adapter, streaming to a fake Scribe
v3 Live (tests/t2_agentic_voice/adapters/live_support.py) with its batch requests to a fake
ElevenLabs, fed a test's steps once the stream has heard its lead; and the frames of a turn."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from t2_agentic_voice.adapters.elevenlabs_live import CHUNK_S
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import Transcribed, Transcribing
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_bridge import TurnSTTBridge
from t2_agentic_voice.voice.stt_requests import SwitchRule
from t2_agentic_voice.voice.stt_stream import CallStream

from tests.t2_agentic_voice.adapters.live_support import BATCH_WORDS, FakeScribe, scribe_stt
from tests.t2_agentic_voice.adapters.provider_support import FakeProvider, answering
from tests.t2_agentic_voice.voice.kit import (
    START_S,
    STOP_S,
    Recorder,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker

# A step of a test's feed: a frame queued, seconds waited, or a call on the bridge.
type Step = Frame | float | Callable[[TurnSTTBridge], None]


@dataclass
class Heard:
    """What a test reads: the session's events, the bridge, the fake Scribe and the batch."""

    session: Recorder
    stt: TurnSTTBridge
    scribe: FakeScribe
    batch: FakeProvider

    def of(self, part: str) -> list[Transcribed]:
        return [e for e in self.session.of(Transcribed) if e.part == part]

    def sent(self) -> list[str]:
        return [e.part for e in self.session.of(Transcribing)]

    def words(self, part: str) -> list[str | None]:
        return [None if e.transcript is None else e.transcript.text for e in self.of(part)]


def heard(
    scribe: FakeScribe,
    steps: Sequence[Step],
    *,
    at_stop: bool = False,
    streaming: bool = True,
    detect: SwitchRule | None = None,
    lead: bool = True,
    turns: int = 1,
    ended: bool = False,
    batch: FakeProvider | None = None,
) -> Heard:
    """The bridge of a talker call (its held request at the hold, or with `at_stop` at the
    detector's stop), named English, fed `steps` once its stream heard its lead (with `lead`:
    silence until the stream is ready, or 2.1 s of it for a call with no stream); returned once
    `turns` turns had their own transcript, or with `ended` once the call ended."""
    batch = batch or FakeProvider(answering(200, {"text": BATCH_WORDS, "language_code": "eng"}))
    events, session = EventStream(SYSTEM_CLOCK), Recorder()
    report = FailureReport(call_id="call-1", emit=lambda event: None, clock=SYSTEM_CLOCK)
    stt = TurnSTTBridge(
        stt=scribe_stt(scribe, batch),
        events=events,
        report=report,
        start_s=START_S,
        early=True,
        at_stop=at_stop,
        detect=detect,
        streaming=streaming,
    )

    async def feed(worker: PipelineWorker) -> None:
        events.start(session)
        stt.listen_in("en")
        if lead:
            await _lead(worker, stt)
        for step in steps:
            if isinstance(step, float):
                await asyncio.sleep(step)
            elif callable(step):
                step(stt)
            else:
                await worker.queue_frame(step)
        if ended:
            await stt.drop()
        else:
            await until(
                lambda: len([e for e in session.of(Transcribed) if e.part == "turn"]) >= turns
            )
        await asyncio.sleep(0.2)  # any answer still to come (none should)
        await events.close()

    asyncio.run(run_pipeline([stt], feed))
    return Heard(session, stt, scribe, batch)


async def _lead(worker: PipelineWorker, stt: TurnSTTBridge) -> None:
    """Silence until the call's stream is ready (2.1 s of it for a call with none)."""
    if not isinstance(stt.stream, CallStream):
        for frame in audio_frames(2.1, loud=False):
            await worker.queue_frame(frame)
        return
    async with asyncio.timeout(10):
        while not stt.stream.ready:
            for frame in audio_frames(0.1, loud=False):
                await worker.queue_frame(frame)
            await asyncio.sleep(0.01)


def loud_s(scribe: FakeScribe) -> list[float]:
    """The seconds of speech (the fakes' tone) in the audio each commit ended, in order."""
    spans: list[float] = []
    loud = 0
    for message in scribe.messages():
        if message["commit"]:
            spans.append(round(loud * CHUNK_S, 2))
            loud = 0
        elif any(base64.b64decode(str(message["audio_base_64"]))):
            loud += 1
    return spans


def opened(speech_s: float = 0.4) -> list[Frame]:
    """A turn's start: a pre-roll of silence, its speech's start, the turn's, its speech."""
    from pipecat.frames.frames import UserStartedSpeakingFrame, VADUserStartedSpeakingFrame

    return [
        *audio_frames(0.5, loud=False),
        *audio_frames(START_S),
        VADUserStartedSpeakingFrame(start_secs=START_S),
        UserStartedSpeakingFrame(),
        *audio_frames(speech_s),
    ]


def stopped() -> list[Frame]:
    """The detector hears the speech stop."""
    from pipecat.frames.frames import VADUserStoppedSpeakingFrame

    return [*audio_frames(STOP_S, loud=False), VADUserStoppedSpeakingFrame(stop_secs=STOP_S)]


def resumed(*, held: bool, speech_s: float = 0.6) -> list[Frame]:
    """The caller speaks again (within the hold, when `held`)."""
    from pipecat.frames.frames import VADUserStartedSpeakingFrame
    from t2_agentic_voice.voice.turn_hold import HoldResumedFrame

    again: list[Frame] = [HoldResumedFrame()] if held else []
    start = VADUserStartedSpeakingFrame(start_secs=START_S)
    return [*audio_frames(START_S), start, *again, *audio_frames(speech_s)]


def closed() -> list[Frame]:
    """The turn's end, after its hold."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    return [*audio_frames(0.2, loud=False), UserStoppedSpeakingFrame()]


def held_turn() -> list[Step]:
    """A whole turn whose hold begins after its stop (Smart Turn's "complete")."""
    from t2_agentic_voice.voice.turn_hold import TurnHeldFrame

    return [*opened(), *stopped(), 0.05, TurnHeldFrame(), *closed()]
