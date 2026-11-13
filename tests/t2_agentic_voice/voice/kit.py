"""What the tests of voice's Pipecat modules share: a speech detector and a turn analyzer that
need no ONNX model, a scripted session in place of `CallSession`, voice's entry point built from
the fakes (tests/t2_agentic_voice/fakes.py and session_fakes.py), and the bound a ticker on the
loop is held to (`TICKER_BOUND_S`).

- `ToneVAD`: a Pipecat `VADAnalyzer` that hears speech in any 20 ms of audio louder than a
  whisper, so the fakes' tone is speech and digital silence is not;
- `PauseAnalyzer`: a Pipecat turn analyzer that calls the first `incomplete` pauses of each
  turn unfinished and every later one the turn's end, as Smart Turn decides at each pause;
- `Script`: the replies of a scripted session (session_fakes.py's `FakeSession`): the
  greeting from the phrase audio once connected, each turn's transcript said back as one
  clause, and a hang-up at the call's end, each reply numbered as the session numbers them;
- `voice_calls`: a `VoiceCalls` of the fakes, its sessions the script's, through the private
  method the entry point builds its sessions with (`_session`, overridden).

It imports Pipecat at its top, after switching its loguru namespace off (`quiet_pipecat`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from tests.t2_agentic_voice.fake_session import FakeSession
from tests.t2_agentic_voice.fakes import (
    FakePhrases,
    FakeSpeechToText,
    FakeTextToSpeech,
    quiet_pipecat,
    tone,
)
from tests.t2_agentic_voice.session_fakes import AGENT

quiet_pipecat()

from aiortc import (  # noqa: E402 - after quiet_pipecat()
    RTCConfiguration,
    RTCDataChannel,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.mediastreams import AudioStreamTrack  # noqa: E402 - after quiet_pipecat()
from pipecat.audio.turn.base_turn_analyzer import (  # noqa: E402 - after quiet_pipecat()
    BaseTurnAnalyzer,
    BaseTurnParams,
    EndOfTurnState,
)
from pipecat.audio.vad.vad_analyzer import (  # noqa: E402 - after quiet_pipecat()
    VADAnalyzer,
    VADParams,
)
from pipecat.frames.frames import (  # noqa: E402 - after quiet_pipecat()
    Frame,
    InputAudioRawFrame,
    StartFrame,
)
from pipecat.metrics.metrics import MetricsData  # noqa: E402 - after quiet_pipecat()
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402 - after quiet_pipecat()
from pipecat.pipeline.worker import PipelineWorker  # noqa: E402 - after quiet_pipecat()
from pipecat.processors.frame_processor import (  # noqa: E402 - after quiet_pipecat()
    FrameDirection,
    FrameProcessor,
)
from pipecat.workers.runner import WorkerRunner  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.core.config import VoiceSettings  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.core.events import Event  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.core.tracing import Tracing  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.domain.declaration import VoiceAgent  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.voice.calls import VoiceCalls  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.voice.pipeline import CallPipeline  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.voice.session.commands import (  # noqa: E402 - after quiet_pipecat()
    Command,
    HangUp,
    ListenIn,
    Speak,
)
from t2_agentic_voice.voice.session.io import Session  # noqa: E402 - after quiet_pipecat()
from t2_agentic_voice.voice.session.session_events import (  # noqa: E402 - after quiet_pipecat()
    Connected,
    Ending,
    SessionEvent,
    Transcribed,
    TransportFailure,
)

# The tone detector's start and stop delays: short, so a test's turns are short.
START_S, STOP_S = 0.1, 0.2
# The bound a 20 ms ticker on the loop is held to while `VoiceCalls.answer` builds a call whose
# detector factory blocks for 0.2 s (test_calls.py): half the block, so a factory run on the loop
# fails it, with room for a machine under load and Windows' 15.6 ms timer (the agent's value).
TICKER_BOUND_S = 0.1


class ToneVAD(VADAnalyzer):
    """Speech wherever 20 ms of audio has a sample louder than 200 (the fakes' tone is 1024)."""

    def __init__(self) -> None:
        params = VADParams(confidence=0.5, start_secs=START_S, stop_secs=STOP_S, min_volume=0.0)
        super().__init__(params=params)

    def num_frames_required(self) -> int:
        return int(self.sample_rate * 0.02)

    def voice_confidence(self, buffer: bytes) -> float:
        samples = memoryview(buffer).cast("h")
        return 1.0 if any(abs(s) > 200 for s in samples) else 0.0


class PauseAnalyzer(BaseTurnAnalyzer):
    """The first `incomplete` pauses of each turn leave it open; the next one ends it."""

    def __init__(self, incomplete: int = 0) -> None:
        super().__init__()
        self.incomplete = incomplete
        self._pauses = 0
        self.decided: list[EndOfTurnState] = []

    @property
    def speech_triggered(self) -> bool:
        return False

    @property
    def params(self) -> BaseTurnParams:
        return BaseTurnParams()

    def append_audio(self, buffer: bytes, is_speech: bool) -> EndOfTurnState:
        return EndOfTurnState.INCOMPLETE

    async def analyze_end_of_turn(self) -> tuple[EndOfTurnState, MetricsData | None]:
        self._pauses += 1
        done = self._pauses > self.incomplete
        state = EndOfTurnState.COMPLETE if done else EndOfTurnState.INCOMPLETE
        if done:
            self._pauses = 0
        self.decided.append(state)
        return state, None

    def clear(self) -> None:
        return None


@dataclass
class Script:
    """A scripted session's replies: the greeting from `phrases` once connected (unless
    `greet` is off), each transcript said back as one clause in `language`, and `HangUp` at
    an `Ending` or a `TransportFailure`. `more` adds commands for an event (after these).
    `sessions` keeps every session built."""

    phrases: FakePhrases
    language: str = "en"
    greet: bool = True
    more: Callable[[SessionEvent], Sequence[Command]] = lambda event: ()
    sessions: list[FakeSession] = field(default_factory=list)
    _next_reply: int = 1

    def replies(self, event: SessionEvent) -> list[Command]:
        out: list[Command] = []
        if isinstance(event, Connected):
            out.append(ListenIn(language="en"))
            if self.greet:
                greeting = AGENT.languages[0].greeting
                audio = self.phrases.audio(greeting, language="en")
                out.append(
                    Speak(
                        reply_id=0,
                        clause=0,
                        turn_id=None,
                        text=greeting,
                        language="en",
                        audio=audio,
                    )
                )
        elif isinstance(event, Transcribed) and event.transcript and event.transcript.text:
            reply, self._next_reply = self._next_reply, self._next_reply + 1
            out.append(
                Speak(
                    reply_id=reply,
                    clause=0,
                    turn_id=event.turn_id,
                    text=event.transcript.text,
                    language="en",
                )
            )
        elif isinstance(event, Ending | TransportFailure):
            reason = event.reason if isinstance(event, Ending) else "transport"
            out.append(HangUp(reason=reason))
        return [*out, *self.more(event)]

    def session(self, pipeline: CallPipeline) -> Session:
        built = FakeSession(pipeline.setup, pipeline.commands, replies=self.replies)
        self.sessions.append(built)
        return built


class ScriptedCalls(VoiceCalls):
    """voice's entry point whose sessions are `script`'s."""

    script: Script

    def _session(self, pipeline: CallPipeline) -> Session:
        return self.script.session(pipeline)


@dataclass
class Built:
    """A `VoiceCalls` of the fakes, with what a test reads of it."""

    calls: ScriptedCalls
    stt: FakeSpeechToText
    tts: FakeTextToSpeech
    phrases: FakePhrases
    script: Script
    emitted: list[Event]
    analyzers: list[PauseAnalyzer]


def voice_calls(
    settings: VoiceSettings,
    *,
    stt: FakeSpeechToText | None = None,
    tts: FakeTextToSpeech | None = None,
    agent: VoiceAgent = AGENT,
    incomplete: int = 0,
    script: Script | None = None,
    speech_detector: Callable[[], VADAnalyzer] = ToneVAD,
) -> Built:
    """voice's entry point of the fakes: the tone detector, a pause analyzer per call (each
    kept), and the script's sessions."""
    phrases = FakePhrases.of(agent)
    script = script or Script(phrases)
    emitted: list[Event] = []
    analyzers: list[PauseAnalyzer] = []

    def analyzer() -> PauseAnalyzer:
        analyzers.append(PauseAnalyzer(incomplete))
        return analyzers[-1]

    stt = stt or FakeSpeechToText()
    tts = tts or FakeTextToSpeech()
    calls = ScriptedCalls(
        agent=agent,
        settings=settings,
        stt=stt,
        tts=tts,
        phrases=phrases,
        tracing=Tracing(),
        emit=emitted.append,
        speech_detector=speech_detector,
        turn_analyzer=analyzer,
    )
    calls.script = script
    return Built(calls, stt, tts, phrases, script, emitted, analyzers)


class Recorder:
    """A session (`Session`) that keeps every event it is handed and gives no command; `closed`
    says whether its stream ended. `block` holds `handle` until it is set (a busy session)."""

    def __init__(self) -> None:
        self.events: list[SessionEvent] = []
        self.closed = False
        self.block: asyncio.Event | None = None

    async def handle(self, event: SessionEvent) -> None:
        if self.block is not None:
            await self.block.wait()
        self.events.append(event)

    async def aclose(self) -> None:
        self.closed = True

    def of[E](self, kind: type[E]) -> list[E]:
        """The events of `kind` handed so far, in order."""
        return [event for event in self.events if isinstance(event, kind)]


async def until(check: Callable[[], bool], *, timeout: float = 10.0) -> None:
    """Return once `check()` holds, looking every 10 ms; TimeoutError after `timeout`."""
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.01)


async def run_pipeline(
    processors: Sequence[FrameProcessor],
    feed: Callable[[PipelineWorker], Awaitable[None]],
    *,
    timeout: float = 30.0,
) -> None:
    """Run a test's pipeline of `processors`: `feed` once it has started, then its cancel."""
    worker = PipelineWorker(
        Pipeline(list(processors)),
        enable_rtvi=False,
        idle_timeout_secs=None,
        cancel_on_idle_timeout=False,
    )
    started = asyncio.Event()

    async def on_started(worker: PipelineWorker, frame: Frame) -> None:
        started.set()

    worker.add_event_handler("on_pipeline_started", on_started)
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    async def go() -> None:
        await started.wait()
        try:
            await feed(worker)
        finally:
            await worker.cancel()

    async with asyncio.timeout(timeout):
        await asyncio.gather(runner.run(), go())


def audio_frames(seconds: float, *, loud: bool = True) -> list[InputAudioRawFrame]:
    """`seconds` of the caller's audio in 20 ms frames: the fakes' tone, or silence."""
    pcm = tone(seconds, 16_000) if loud else bytes(round(seconds * 16_000) * 2)
    return [
        InputAudioRawFrame(audio=pcm[i : i + 640], sample_rate=16_000, num_channels=1)
        for i in range(0, len(pcm), 640)
    ]


async def client_offer() -> tuple[RTCPeerConnection, RTCDataChannel, str]:
    """A local aiortc peer with no ICE server (tests/conftest.py makes aiortc's default list
    raise), sending a silent audio track, with a data channel: its peer, channel and offer."""
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    peer.addTrack(AudioStreamTrack())
    channel = peer.createDataChannel("t2v")
    await peer.setLocalDescription(await peer.createOffer())
    return peer, channel, peer.localDescription.sdp


async def client_answered(peer: RTCPeerConnection, answer: str) -> None:
    """Give the local peer the server's answer."""
    await peer.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))


class Tail(FrameProcessor):
    """The end of a test's pipeline: keeps every frame that reaches it, each way, but the
    start, and passes it on."""

    def __init__(self) -> None:
        super().__init__(name="tail")
        self.frames: list[tuple[Frame, FrameDirection]] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if not isinstance(frame, StartFrame):
            self.frames.append((frame, direction))
        await self.push_frame(frame, direction)

    def of[F](
        self, kind: type[F], direction: FrameDirection = FrameDirection.DOWNSTREAM
    ) -> list[F]:
        """The frames of `kind` that came `direction`, in order."""
        return [f for f, d in self.frames if isinstance(f, kind) and d == direction]
