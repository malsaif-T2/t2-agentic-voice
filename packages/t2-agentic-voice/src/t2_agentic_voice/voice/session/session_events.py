"""The session's events: what voice's Pipecat modules tell one call's session, each handed to
`Session.handle` in the order it happened (plan 003, step 10). io.py says how the two sides
meet (times, turns, replies, the drop rule, the stop path, the taps, the messages, the failures
and the end); the session's commands are commands.py's. Frozen dataclasses with no Pipecat
type: they are internal, and the taps run at about 50 a second.

Every event carries `at`, when it happened on the call's `Clock`. A turn's events carry the
caller's `turn_id`, from the speech-to-text bridge; a clause's carry the agent's `reply_id` and
the clause's index in it, from the session's `Speak`. A request to a provider is reported when
it goes (`Transcribing`, `Synthesizing`), so the session counts every request that went, one
the call's end cancelled included (io.py's usage).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import EndReason, TransportStage, TurnId
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.voice.protocol import ClauseIndex, ClientMessage, ReplyId

# Which of a turn's speech-to-text requests a `Transcribing` or a `Transcribed` is: the `turn`,
# its whole speech at its end, which every turn has; for an overlap (`HearOverlap`), its
# `window`, the first part of the speech over the agent's, or the `overlap`, all of it (io.py's
# overlaps); or, in a call with a talker, the `held` request of a turn said while the agent was
# silent, its speech so far sent when its hold began (`TurnHeld`, plan 006's early start).
TranscriptPart = Literal["window", "overlap", "turn", "held"]


@dataclass(frozen=True, kw_only=True)
class Connected:
    """The caller's peer connected. Messages sent before its data channel opens are queued for
    it by the transport."""

    at: float


@dataclass(frozen=True, kw_only=True)
class TurnOpened:
    """The caller began a turn: `turn_id`, its number in the call, from 0; `speech_at`, when the
    speech detector heard its speech begin, which the turn's opening follows by the detector's
    start delay and more (the spike's 0.34 s). The session compares `speech_at` with when the
    agent last spoke, any reply, the greeting included (io.py's drop rule)."""

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
class TurnHeld:
    """Smart Turn called the caller's turn complete, and its hold began (voice/turn_hold.py): in
    a call with a talker, the speech-to-text bridge sends the turn's speech so far as its `held`
    request now, and the session starts the talker on its transcript (plan 006, Q2), playing
    nothing before the hold ends with the turn's `TurnClosed`. Given only for a turn that is no
    overlap, and only in a call with a talker."""

    turn_id: TurnId
    at: float


@dataclass(frozen=True, kw_only=True)
class HoldResumed:
    """The caller spoke again within the hold of the turn `turn_id`: what the session started
    early for it is cancelled (the `held` request too, its `Transcribed` never handed after
    this), and the turn goes on, what follows joined to it, its own request holding all of it
    (plan 006, Q2). It follows a `TurnHeld` of the turn, once."""

    turn_id: TurnId
    at: float


@dataclass(frozen=True, kw_only=True)
class Transcribing:
    """The speech-to-text bridge sent a turn's request, at `at`, with `audio_s` seconds of its
    audio: handed as the request goes, before the `Transcribed` of the same `part`, and whatever
    comes of it, so a request the call's end cancels is still counted (io.py's usage)."""

    turn_id: TurnId
    at: float
    audio_s: float
    part: TranscriptPart = "turn"


@dataclass(frozen=True, kw_only=True)
class Transcribed:
    """A turn's one speech-to-text result: its `transcript` (with the headroom the provider
    reported for its key, when the adapter reads it), None when the request failed (`failure`,
    a `ProviderError`'s kind, and whether asking again may succeed) or when no audio was sent;
    `audio_s`, the seconds of audio sent; `sent_at`, when the request went (its `Transcribing`'s
    `at`; None when none went); `at`, when the answer came; and `part`, which of the turn's
    requests it answers (an overlap's turn may reuse its `overlap` transcript as its `turn`'s,
    with no request: io.py's overlaps)."""

    turn_id: TurnId
    at: float
    audio_s: float
    sent_at: float | None
    transcript: Transcript | None
    failure: ProviderErrorKind | None = None
    retryable: bool = False
    part: TranscriptPart = "turn"


@dataclass(frozen=True, kw_only=True)
class Synthesizing:
    """The text-to-speech bridge sent a clause's request, at `at`, its text the `Speak`'s:
    handed as the request goes, before the clause's other events, and whatever comes of it, so
    a request the call's end cancels is still counted (io.py's usage). A cached phrase sends
    none."""

    reply_id: ReplyId
    clause: ClauseIndex
    at: float


@dataclass(frozen=True, kw_only=True)
class ClauseQueued:
    """The first audio of a clause the session asked for came, from the provider or the phrase
    cache, and was queued for the output: `requested_at`, when its text-to-speech request went
    (its `Synthesizing`'s `at`; None for a cached phrase, which sends none), so the first audio
    took `at - requested_at`."""

    reply_id: ReplyId
    clause: ClauseIndex
    at: float
    requested_at: float | None


@dataclass(frozen=True, kw_only=True)
class ClausePlayed:
    """The last audio of a clause left the output transport (the browser plays it a jitter
    buffer later, and says so in a `playback` message): how many seconds of audio came, in how
    many chunks; the headroom the provider reported on the response's first chunk (none for a
    cached phrase); and whether the take came back cut short (on its last)."""

    reply_id: ReplyId
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

    reply_id: ReplyId
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
    """A message of the client's, parsed by the Pipecat side with `parse_client_message`, given
    the transport's `on_app_message` object as it is (Pipecat parsed its text: the protocol's
    object path). One that is not exactly one of `t2v/1`'s is logged with no content and
    dropped, never handed on."""

    message: ClientMessage
    at: float


@dataclass(frozen=True, kw_only=True)
class TransportFailure:
    """The call's connection failed at `stage`: `connect` when ICE failed or voice's own deadline
    from offer to connected passed (items 11 and 21), `media` when the path dropped after it
    connected (aioice's consent checks give up in about 30 s). It ends the call: only the
    report of a request that went before it may follow (io.py's end)."""

    stage: TransportStage
    at: float


@dataclass(frozen=True, kw_only=True)
class Ending:
    """The call ends from outside the session, for `reason`: the caller's side closed the
    connection (`caller_left`), or voice's entry point was asked to end it (`server`: the
    runtime is stopping). It ends the call: only the report of a request that went before it
    may follow (io.py's end)."""

    reason: EndReason
    at: float


SessionEvent = (
    Connected
    | TurnOpened
    | TurnHeld
    | HoldResumed
    | TurnClosed
    | Transcribing
    | Transcribed
    | Synthesizing
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
    TurnHeld,
    HoldResumed,
    TurnClosed,
    Transcribing,
    Transcribed,
    Synthesizing,
    ClauseQueued,
    ClausePlayed,
    ClauseFailed,
    CallerAudio,
    AgentAudio,
    FromClient,
    TransportFailure,
    Ending,
)
