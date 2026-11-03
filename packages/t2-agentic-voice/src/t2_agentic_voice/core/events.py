"""What a call reports to the team's code: its events and, when it ends, its `CallReport` (the
design's 6.6). Types every layer shares (ARCHITECTURE.md, "Conventions"): `voice` builds them,
`api` hands them to the observers a team registers, and an app reads them through the `events`
facade. Provisional.

Every event is frozen, from a closed list (`EVENTS`), and carries the call's ID, its turn's
(None for an event of the whole call) and when it happened. Observers run off the call's path
and cannot change it. These are the events the echo session emits; the design's others (`Busy`,
the tools' and the actions' events, `GuardBlocked`) come with what they report.

An event and the report hold what was heard and said, so neither is ever logged (call content
is logged at no level, docs/SECURITY.md, invariant 8); the report's numbers are written apart,
with no text.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.settings.tts import LanguageTag

# A call's ID: URL-safe characters, as the router mints it. It names the call in traces
# (`session.id`), events, logs and the `hello` message, so it is never a credential (the
# design's 5.5).
CALL_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
# The largest turn number or index a message may carry: a 32-bit signed integer's, which every
# client language holds exactly.
MAX_INDEX = 2**31 - 1
# The longest duration a client reports, in milliseconds: a day (the agent's bound, far over
# any call).
MAX_MS = 86_400_000.0

CallId = Annotated[str, Field(pattern=CALL_ID_PATTERN)]
# A turn's number in its call, from 0, as the speech-to-text bridge stamps it.
TurnId = Annotated[int, Field(ge=0, le=MAX_INDEX)]
_Ms = Annotated[float, Field(ge=0, le=MAX_MS, allow_inf_nan=False)]

# Why a call ended: the caller hung up; the caller's side closed the connection; the call
# reached `limits.max_call_s`, or `limits.idle_s` with nothing heard; the connection failed;
# the server stopped or failed.
EndReason = Literal["hangup", "caller_left", "max_call", "idle", "transport", "server"]
# How an interruption ended the agent's speech (the design's 6.6); the echo session has only
# `stop`, the Stop button or Esc, and the others come with the interruption rules.
InterruptionKind = Literal["stop", "correction", "new_words", "false"]
# Where a call's connection failed: its offer could not be answered; it never connected (ICE
# failed, or the offer-to-connected deadline passed); or it dropped after it connected.
TransportStage = Literal["offer", "connect", "media"]
# The kind of the ICE candidate the browser's call selected (host, server reflexive, peer
# reflexive, relayed), and how a relayed one reaches its TURN server.
CandidateType = Literal["host", "srflx", "prflx", "relay"]
RelayProtocol = Literal["udp", "tcp", "tls"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClientConnection(_Frozen):
    """The browser's view of its connection, from its `client_stats` message: the selected
    candidate's type and, for a relay, how it reaches the TURN server and on which port; how
    long it took to connect; whether the microphone's echo cancellation applied; and how long
    after connecting the first audio played. A value the browser did not report is None."""

    candidate_type: CandidateType | None = None
    relay_protocol: RelayProtocol | None = None
    turn_port: int | None = Field(default=None, ge=1, le=65535)
    connect_ms: _Ms | None = None
    echo_cancellation: bool | None = None
    first_audio_ms: _Ms | None = None

    @model_validator(mode="after")
    def _relay_only(self) -> ClientConnection:
        if self.candidate_type != "relay" and (self.relay_protocol or self.turn_port):
            raise ValueError("relay_protocol and turn_port belong to a relay candidate only")
        return self


class TurnTimes(_Frozen):
    """How long a turn's steps took, in milliseconds, each None when it did not happen: from the
    turn's end to its first audio (`ttfa_ms`), to the transcript (`stt_ms`), to the chat model's
    first token (none before the talker), and from a text-to-speech request to its first audio."""

    ttfa_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stt_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    llm_first_token_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tts_first_audio_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ModelUsage(_Frozen):
    """One provider model's use in one call: its requests, each counted once it went, answered
    or not (one the call's end cancelled included); for speech-to-text, the audio seconds sent
    and billed (at least 10 s a request, as Groq bills Whisper); for text-to-speech, the
    characters sent and the phrases played from the cache, which sent nothing; and the last
    headroom the provider reported for its key."""

    model: str = Field(min_length=1)
    requests: int = Field(default=0, ge=0)
    audio_sent_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    billed_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    characters: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)


class TurnRecord(_Frozen):
    """One turn of a call: what was heard, in which language, and what the agent said back;
    whether the turn was dropped (its speech began while the agent spoke, the greeting included,
    or just after), its reply stopped by the caller, or the turn left unfinished (the call ended
    before its transcript came, so nothing was heard); and its times."""

    turn_id: TurnId
    language: LanguageTag | None = None
    heard: str
    said: str = ""
    dropped: bool = False
    stopped: bool = False
    unfinished: bool = False
    times: TurnTimes = Field(default_factory=TurnTimes)


class CallReport(_Frozen):
    """What one call did, given to `CallEnded`'s observers: who answered it (the agent's name),
    when it started and ended and why, the consent version the caller agreed to, each turn
    (what was heard and said, and its times), each model's usage (every request the call sent,
    one its end cancelled included, so a cap set from `requests_per_minute` counts what the key
    was asked), and the browser's view of the connection. The tool calls, the actions and the
    agent's fingerprint come with the talker and the actions."""

    call_id: CallId
    agent: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    ended_by: EndReason
    consent_version: str | None = None
    turns: tuple[TurnRecord, ...] = ()
    usage: tuple[ModelUsage, ...] = ()
    client: ClientConnection | None = None

    @model_validator(mode="after")
    def _consistent(self) -> CallReport:
        if self.ended_at < self.started_at:
            raise ValueError("a call ends after it starts")
        models = [each.model for each in self.usage]
        if len(set(models)) != len(models):
            raise ValueError("each model's usage is counted in one entry")
        return self

    @property
    def duration_s(self) -> float:
        """How long the call lasted."""
        return (self.ended_at - self.started_at).total_seconds()

    def requests_per_minute(self) -> dict[str, float]:
        """Each model's requests per call minute, the measure a cap on live calls is set from;
        0 for a call that lasted no time."""
        minutes = self.duration_s / 60
        return {u.model: u.requests / minutes if minutes else 0.0 for u in self.usage}


class Event(_Frozen):
    """What every event carries: the call's ID, its turn's (None for an event of the whole
    call), and when it happened."""

    call_id: CallId
    turn_id: TurnId | None = None
    at: AwareDatetime


class _TurnEvent(Event):
    turn_id: TurnId


class CallStarted(Event):
    """The call connected and its session began."""


class CallEnded(Event):
    """The call ended; `report` says what it did."""

    report: CallReport


class UserTurnEnded(_TurnEvent):
    """The caller finished a turn, and `heard` is its transcript (empty when nothing was heard)."""

    heard: str


class Interrupted(Event):
    """The agent's reply was cut off, and how; its `turn_id` is the caller's turn the reply
    answered, None for the greeting or a spoken notice, which answer none."""

    kind: InterruptionKind


class AgentSpeechEnded(Event):
    """The agent's reply ended: `text` is what it was to say, `played_fraction` how much of its
    audio played (1 when it played whole); its `turn_id` is the caller's turn the reply
    answered, None for the greeting or a spoken notice, which answer none."""

    text: str
    played_fraction: float = Field(ge=0, le=1, allow_inf_nan=False)


class ProviderFailed(Event):
    """A provider (speech-to-text, text-to-speech) failed a request of the call, `kind` from
    `ProviderError`'s closed list."""

    kind: ProviderErrorKind
    retryable: bool


class TransportFailed(Event):
    """The call's connection failed at `stage`."""

    stage: TransportStage


class TurnMetrics(TurnTimes, _TurnEvent):
    """How long a turn's steps took (its `TurnTimes`)."""


# The events a call emits, in the order the design's 6.6 lists them.
EVENTS: tuple[type[Event], ...] = (
    CallStarted,
    CallEnded,
    UserTurnEnded,
    Interrupted,
    AgentSpeechEnded,
    ProviderFailed,
    TransportFailed,
    TurnMetrics,
)
