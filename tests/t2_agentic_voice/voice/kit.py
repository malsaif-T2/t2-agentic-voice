"""What Track E's tests of voice's Pipecat modules share: a speech detector and a turn analyzer
that need no ONNX model, a scripted session in place of `CallSession` (Track D's), and voice's
entry point built from the fakes (tests/t2_agentic_voice/fakes.py and session_fakes.py).

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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, quiet_pipecat
from tests.t2_agentic_voice.session_fakes import AGENT, FakePhrases, FakeSession

quiet_pipecat()

from pipecat.audio.turn.base_turn_analyzer import (  # noqa: E402
    BaseTurnAnalyzer,
    BaseTurnParams,
    EndOfTurnState,
)
from pipecat.audio.vad.vad_analyzer import VADAnalyzer, VADParams  # noqa: E402
from pipecat.metrics.metrics import MetricsData  # noqa: E402
from t2_agentic_voice.core.config import VoiceSettings  # noqa: E402
from t2_agentic_voice.core.events import Event  # noqa: E402
from t2_agentic_voice.core.tracing import Tracing  # noqa: E402
from t2_agentic_voice.domain.declaration import VoiceAgent  # noqa: E402
from t2_agentic_voice.voice.calls import VoiceCalls  # noqa: E402
from t2_agentic_voice.voice.pipeline import CallPipeline  # noqa: E402
from t2_agentic_voice.voice.session.commands import (  # noqa: E402
    Command,
    HangUp,
    ListenIn,
    Speak,
)
from t2_agentic_voice.voice.session.io import Session  # noqa: E402
from t2_agentic_voice.voice.session.session_events import (  # noqa: E402
    Connected,
    Ending,
    SessionEvent,
    Transcribed,
    TransportFailure,
)

# The tone detector's start and stop delays: short, so a test's turns are short.
START_S, STOP_S = 0.1, 0.2


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
    an `Ending` or a `TransportFailure`. `extra` adds commands for an event (after these).
    `sessions` keeps every session built."""

    phrases: FakePhrases
    language: str = "en"
    greet: bool = True
    extra: Callable[[SessionEvent], Sequence[Command]] = lambda event: ()
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
                        reply_id=0, clause=0, turn_id=None, text=greeting, language="en",
                        audio=audio,
                    )
                )
        elif isinstance(event, Transcribed) and event.transcript and event.transcript.text:
            reply, self._next_reply = self._next_reply, self._next_reply + 1
            out.append(
                Speak(
                    reply_id=reply, clause=0, turn_id=event.turn_id,
                    text=event.transcript.text, language="en",
                )
            )
        elif isinstance(event, Ending | TransportFailure):
            reason = event.reason if isinstance(event, Ending) else "transport"
            out.append(HangUp(reason=reason))
        return [*out, *self.extra(event)]

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
        speech_detector=ToneVAD,
        turn_analyzer=analyzer,
    )
    calls.script = script
    return Built(calls, stt, tts, phrases, script, emitted, analyzers)
