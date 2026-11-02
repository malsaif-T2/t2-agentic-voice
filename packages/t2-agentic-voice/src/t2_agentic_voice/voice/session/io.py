"""The session's I/O: the commands and events between one call's session (`voice/session/`, which
imports no Pipecat: ARCH-BAN) and voice's Pipecat modules, so each side builds against this
module alone (plan 003, step 10; Track D builds the session, Track E the Pipecat side).

The Pipecat side (the transport, the speech detector and the turn analyzer, the speech bridges,
the session bridge) tells the session what happened: each `SessionEvent` goes to
`Session.handle`, one at a time, in the order it happened. The session answers with `Command`s,
which the Pipecat side carries out in order (`Commands.run`). Neither holds a Pipecat type. The
items cited are plan 003's appendix, "Changes to the plan's interfaces".

- **Times.** Every event carries `at`, when it happened, in seconds on the call's `Clock`
  (`time.perf_counter` in a call, a fake clock in a test): the processors' own stamps, never
  Pipecat's `timestamp` fields, which step at 15.625 ms on Windows (item 6). The session reads
  the same clock, for its timers too.
- **Turns** are keyed on the frames, never on `UserTurnProcessor`'s events, which run on tasks of
  their own, unordered against the frames (item 6): the speech-to-text bridge numbers each turn
  from 0 when its `UserStartedSpeakingFrame` reaches it, and stamps the number on the turn's end
  and its transcript, since the next turn's start can reach the session before the last turn's
  transcript. Each `TurnOpened` is followed by one `TurnClosed` and exactly one `Transcribed`,
  in either order, an empty, failed or unusable result included (item 4).
- **Clauses.** The session speaks a reply clause by clause (`Speak`), each within the provider's
  `max_chars`, so the text-to-speech bridge's TOKEN aggregation sends one request per clause
  (item 9). Each clause reports `ClauseQueued` when its first audio is queued for the output,
  then `ClausePlayed` or `ClauseFailed`, unless a `StopSpeaking` drops it first.
- **The stop path** (item 7). `StopSpeaking` drops the agent's speech at once: the session
  bridge, upstream of the text-to-speech bridge, calls `broadcast_interruption()`, and every
  processor drops its queued frames up to the output transport. Up to about 40 ms already in the
  WebRTC track still plays, so "no audio frame of that turn is sent after a stop" holds at the
  output transport. Pipecat's own interruptions stay off: only the session stops speech.
- **Taps** (item 15). `CallerAudio` is the caller's audio as the pipeline hears it, taken after
  the transport, and `AgentAudio` the agent's as the output transport sends it: what the call's
  recorder writes, and only when the setting and a signed consent both allow it (invariant 8).
  The taps always flow; the recorder decides.
- **Messages.** The client's messages reach the session parsed (`FromClient`, voice/protocol.py),
  and the session's go out as `Send`, an urgent transport message a stop never drops (item 8).
- **Failures** (item 12). A connection that fails, or is not connected within voice's own
  deadline from offer to connected, is a `TransportFailure`: ICE failure pushes no error frame,
  so it comes from the connection's events. A provider's failure comes on the turn's or the
  clause's own event.
- **The end.** The session's last command is always `HangUp`, whatever ended the call: the
  caller's `hangup`, a limit, a `TransportFailure` or an `Ending`. No event follows it.

What else a session needs (the agent, the settings, the phrase cache, tracing, where its public
events go) comes in its `CallSetup`, from voice's entry point (`voice/calls.py`).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import CallId, EndReason, Event, TransportStage, TurnId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import ClauseIndex, ClientMessage, SessionMessage

# Where the session's public events go (core/events.py): the runtime's observers, queued off the
# call's path (the design's 6.6). It returns at once and never raises.
EventSink = Callable[[Event], None]


class Clock(Protocol):
    """A call's time: `now`, on the scale every event's `at` is on; `wall`, the time of day the
    public events and the report carry; and `sleep`, for the session's timers."""

    def now(self) -> float:
        """Seconds on a monotonic scale with no fixed start."""

    def wall(self) -> datetime:
        """The time of day now, aware (UTC)."""

    async def sleep(self, seconds: float) -> None:
        """Return once `seconds` have passed on this clock."""


class SystemClock:
    """The clock of a real call: `time.perf_counter`, whose resolution is far finer than
    `time.monotonic`'s 15.6 ms on Windows (plan 003's decision log), the system's UTC time, and
    asyncio's sleep."""

    def now(self) -> float:
        return time.perf_counter()

    def wall(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


SYSTEM_CLOCK = SystemClock()


class Phrases(Protocol):
    """The runtime's fixed phrases (the greetings, the echo's frames, the notices), each
    synthesized once at the runtime's start and kept (adapters/phrase_cache.py's `PhraseCache`)."""

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        """A declared phrase's audio in `language`'s voice, from memory, with no request.
        LookupError for any text not declared at the start: no heard words reach the cache
        (invariant 8)."""


# What the Pipecat side tells the session.


@dataclass(frozen=True, kw_only=True)
class Connected:
    """The caller's peer connected. Messages sent before its data channel opens are queued for
    it by the transport."""

    at: float


@dataclass(frozen=True, kw_only=True)
class TurnOpened:
    """The caller began a turn: `turn_id`, its number in the call, from 0; `speech_at`, when the
    speech detector heard its speech begin, which the turn's opening follows by the detector's
    start delay and more (the spike's 0.34 s), and which the session compares with when the
    agent last spoke."""

    turn_id: TurnId
    at: float
    speech_at: float


@dataclass(frozen=True, kw_only=True)
class TurnClosed:
    """The caller's turn ended, as the turn analyzer decided: `speech_ended_at`, when the speech
    detector last heard the speech stop before it, so the analyzer's decision (Smart Turn's, or
    its fallback's) took `at - speech_ended_at`."""

    turn_id: TurnId
    at: float
    speech_ended_at: float


@dataclass(frozen=True, kw_only=True)
class Transcribed:
    """A turn's one speech-to-text result: its `transcript`, None when the request failed
    (`failure`, a `ProviderError`'s kind, and whether asking again may succeed) or when no audio
    was sent; `audio_s`, the seconds of audio sent; `sent_at`, when the request went (None when
    none did); and `at`, when the answer came."""

    turn_id: TurnId
    at: float
    audio_s: float
    sent_at: float | None
    transcript: Transcript | None
    failure: ProviderErrorKind | None = None
    retryable: bool = False


@dataclass(frozen=True, kw_only=True)
class ClauseQueued:
    """The first audio of a clause the session asked for came, from the provider or the phrase
    cache, and was queued for the output: `requested_at`, when its text-to-speech request went
    (None for a cached phrase, which sends none), so the first audio took `at - requested_at`."""

    turn_id: TurnId
    clause: ClauseIndex
    at: float
    requested_at: float | None


@dataclass(frozen=True, kw_only=True)
class ClausePlayed:
    """The last audio of a clause left the output transport (the browser plays it a jitter
    buffer later, and says so in a `playback` message): how many seconds of audio came, in how
    many chunks; the headroom the provider reported on the response's first chunk (none for a
    cached phrase); and whether the take came back cut short (on its last)."""

    turn_id: TurnId
    clause: ClauseIndex
    at: float
    audio_s: float
    chunks: int
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    cut_short: bool = False


@dataclass(frozen=True, kw_only=True)
class ClauseFailed:
    """A clause's text-to-speech request failed, with a `ProviderError` of `failure`'s kind: no
    more of the clause plays."""

    turn_id: TurnId
    clause: ClauseIndex
    at: float
    failure: ProviderErrorKind
    retryable: bool


@dataclass(frozen=True, kw_only=True)
class CallerAudio:
    """The input tap: a piece of the caller's audio as the pipeline hears it, after the
    transport, mono PCM16 at `sample_rate` (16 kHz, the speech detector's rate: item 15)."""

    pcm16: bytes
    sample_rate: int
    at: float


@dataclass(frozen=True, kw_only=True)
class AgentAudio:
    """The output tap: a piece of the agent's audio as the output transport sends it, mono PCM16
    at `sample_rate`, the pipeline's output rate."""

    pcm16: bytes
    sample_rate: int
    at: float


@dataclass(frozen=True, kw_only=True)
class FromClient:
    """A message of the client's, parsed by the Pipecat side (`parse_client_message`, given the
    transport's `on_app_message` object as it is). One that is not exactly one of `t2v/1`'s is
    logged with no content and dropped, never handed on."""

    message: ClientMessage
    at: float


@dataclass(frozen=True, kw_only=True)
class TransportFailure:
    """The call's connection failed at `stage`: `connect` when ICE failed or voice's own deadline
    from offer to connected passed (items 11 and 21), `media` when the path dropped after it
    connected (aioice's consent checks give up in about 30 s)."""

    stage: TransportStage
    at: float


@dataclass(frozen=True, kw_only=True)
class Ending:
    """The call ends from outside the session, for `reason`: the caller's side closed the
    connection (`caller_left`), or voice's entry point was asked to end it (`server`: the
    runtime is stopping)."""

    reason: EndReason
    at: float


SessionEvent = (
    Connected
    | TurnOpened
    | TurnClosed
    | Transcribed
    | ClauseQueued
    | ClausePlayed
    | ClauseFailed
    | CallerAudio
    | AgentAudio
    | FromClient
    | TransportFailure
    | Ending
)
SESSION_EVENTS: tuple[type[SessionEvent], ...] = (
    Connected,
    TurnOpened,
    TurnClosed,
    Transcribed,
    ClauseQueued,
    ClausePlayed,
    ClauseFailed,
    CallerAudio,
    AgentAudio,
    FromClient,
    TransportFailure,
    Ending,
)


# What the session asks of the Pipecat side.


@dataclass(frozen=True, kw_only=True)
class ListenIn:
    """The language the speech-to-text bridge names to the provider for every turn from now on:
    a `Language`'s `primary` code (`ar`, `en`) under `stt.live_language = "session"`, or None
    under `auto`, when the provider detects it. Until the first, none is named."""

    language: str | None


@dataclass(frozen=True, kw_only=True)
class Speak:
    """Say one clause of a turn's reply in the voice of `language`: `text`, at most the
    provider's `max_chars`, in one text-to-speech request; or, for a fixed phrase, `audio` from
    the phrase cache, played with no request (`text` kept for its caption and its span).
    Clauses play in the order they were asked for."""

    turn_id: TurnId
    clause: ClauseIndex
    text: str
    language: LanguageTag
    audio: AudioChunk | None = None


@dataclass(frozen=True, kw_only=True)
class StopSpeaking:
    """Drop the agent's speech at once, every clause queued or playing (the stop path, above): no
    audio frame of `turn_id`'s reply reaches the output transport after it, and no event of a
    dropped clause follows."""

    turn_id: TurnId


@dataclass(frozen=True, kw_only=True)
class Send:
    """Send the client `message` at once, ahead of any queued audio: an urgent transport message,
    which a stop never drops (item 8)."""

    message: SessionMessage


@dataclass(frozen=True, kw_only=True)
class HangUp:
    """End the call, for `reason`: the session's last command, after its `ended` message. The
    Pipecat side closes the peer, the close bounded by a timeout (item 20), and ends the
    pipeline; no event follows."""

    reason: EndReason


Command = ListenIn | Speak | StopSpeaking | Send | HangUp
COMMANDS: tuple[type[Command], ...] = (ListenIn, Speak, StopSpeaking, Send, HangUp)


class Session(Protocol):
    """One call's session as the Pipecat side drives it (voice/session/call.py's `CallSession`)."""

    async def handle(self, event: SessionEvent) -> None:
        """Take one event, in the order they happened, and return soon: what takes longer (a
        timer, a report written to disk) runs on the session's own tasks. Never raises."""


class Commands(Protocol):
    """Where the session's commands go: the Pipecat side, which carries each out (the session
    bridge)."""

    async def run(self, command: Command) -> None:
        """Carry out `command`, after every command before it. Never raises: what fails comes
        back as an event."""


@dataclass(frozen=True, kw_only=True)
class CallSetup:
    """What one call's session starts with, from voice's entry point: the call's ID; who is
    calling and what they consented to, as the identity source verified them at join; the agent
    and the settings; the runtime's phrase cache; the most characters one text-to-speech request
    of a language takes (the provider's `max_chars`, which the clause splitter honours); the
    runtime's tracing; where the session's public events go; and the call's clock."""

    call_id: CallId
    caller: Caller
    consent: Consent
    agent: VoiceAgent
    settings: VoiceSettings
    phrases: Phrases
    max_chars: Callable[[str], int | None]
    tracing: Tracing
    emit: EventSink
    clock: Clock = SYSTEM_CLOCK
