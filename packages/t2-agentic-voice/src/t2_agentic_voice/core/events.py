"""What a call reports to the team's code: its events and, when it ends, its `CallReport` (the
design's 6.6). Types every layer shares (ARCHITECTURE.md, "Conventions"): `voice` builds them,
`api` hands them to the observers a team registers, and an app reads them through the `events`
facade. Provisional.

Every event is frozen, from a closed list (`EVENTS`), and carries the call's ID, its turn's
(None for an event of the whole call) and when it happened. Observers run off the call's path
and cannot change it. These are the events the session emits, the talker's among them (a tool
call begun and ended, a clause the output guard blocked: plan 006); the design's others
(`Busy`) come with what they report; the actions' are declared here for plan 007's tracks.

An event and the report hold what was heard and said (a tool's arguments and result, a
read-back's draft and a write's result among it), so neither is ever logged (call content is
logged at no level, docs/SECURITY.md, invariant 8); the report's numbers are written apart, with
no text.
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
# A reply's number in its call, from 0, as the session counts them: the greeting is reply 0.
ReplyId = Annotated[int, Field(ge=0, le=MAX_INDEX)]
# A clause's index in its reply, from 0.
ClauseIndex = Annotated[int, Field(ge=0, le=MAX_INDEX)]
_Ms = Annotated[float, Field(ge=0, le=MAX_MS, allow_inf_nan=False)]

# Why a call ended: the caller hung up; the caller's side closed the connection; the call
# reached `limits.max_call_s`, or `limits.idle_s` with nothing heard; the connection failed;
# the server stopped or failed.
EndReason = Literal["hangup", "caller_left", "max_call", "idle", "transport", "server"]
# How an interruption ended the agent's speech (the design's 6.6); the echo session has only
# `stop`, the Stop button or Esc, and the others come with the interruption rules.
InterruptionKind = Literal["stop", "correction", "new_words", "false"]
# Which step of the interruption rule decided (domain/interruptions.py's `VerdictReason` is this
# list), in the rule's order, or `model`, the chat model's stop on an overlap the rule left
# uncertain (D-069): for the trace and the scorecards, never the words themselves.
InterruptionReason = Literal[
    "no_words",
    "stop_word",
    "repeat_word",
    "own_words",
    "listening",
    "short_output",
    "enough_words",
    "too_few_words",
    "model",
]
# Why the output guard blocked a clause (the design's 8.2): an ID-shaped token with no evidence
# (rule B), or a claim the record and a status result do not hold (rule A). Text after an action
# call (rule C) is dropped silently, never blocked.
GuardReason = Literal["unsupported_id", "unsupported_claim"]
# What the yes rule made of a read-back's answer.
ConfirmationDecision = Literal["yes", "declined", "correction", "asked_again"]
# How a write ended when no record of it could be made: definitely not done, or unknown.
UnconfirmedKind = Literal["failed", "unknown"]
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
    """How long a turn's steps took, in milliseconds, each None when it did not happen. From the
    end of the caller's speech (the speech detector's stop less its stop delay): to the first
    audible frame of the reply sent (`ttfa_ms`; a silent first chunk is not audible, TD-090; a
    call whose output taps no audio, a test's or `TextCall`'s, times its first audio queued), a
    progress line counted apart (`progress_ms`, the first audible frame of one); to the
    browser's playback of the reply (`played_ms`, from its `playback` report, when it sends
    one); to the chat model's first token (`llm_first_token_ms`, the talker's); to the turn's
    end, as the turn analyzer closed it (`end_of_turn_ms`: the detector's stop delay, Smart
    Turn's judgement and the hold after it); and to Smart Turn's "complete", where the hold
    began (`turn_complete_ms`, in a call with a talker, for a turn said while the agent was
    silent). From the detector's stop as it came, to the transcript (`stt_ms`: the turn's own
    request's, or its held request's when it took that one as its own, in a call with a
    talker); and from a text-to-speech request to its first audio (`tts_first_audio_ms`)."""

    ttfa_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stt_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    llm_first_token_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tts_first_audio_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    progress_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    played_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end_of_turn_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    turn_complete_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ModelUsage(_Frozen):
    """One provider model's use in one call: its requests, each counted once it went, answered
    or not (one the call's end cancelled included); for speech-to-text, the audio seconds sent
    and billed (at least 10 s a request, as Groq bills Whisper); for text-to-speech, the
    characters sent and the cache's hits, the phrases and the clauses played from the caches,
    which sent nothing; for the chat model, the tokens read (the cached ones counted again in
    `cached_tokens`) and written, as each request's provider reported them; and the last
    headroom the provider reported for its key."""

    model: str = Field(min_length=1)
    requests: int = Field(default=0, ge=0)
    audio_sent_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    billed_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    characters: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
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
    answered, None for the greeting or a spoken notice, which answer none; and `reason`, the
    step of the interruption rule that decided it, None when no rule did (the Stop button or
    Esc, the only interruption under `interruptions.mode = "drop"`)."""

    kind: InterruptionKind
    reason: InterruptionReason | None = None


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


class ToolStarted(_TurnEvent):
    """The talker called the tool `tool` in its reply to the turn; `tool_call_id` is the
    model's id for the call, and `arguments` the JSON text the model wrote for it (call
    content: a search's words)."""

    tool: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    arguments: str = ""


class ToolFinished(ToolStarted):
    """The tool call ended: whether it succeeded (`ok`: a `ToolError`, any other failure or its
    timeout is not), how long it ran, in milliseconds on the call's clock, what it gave the
    model back (`result`, JSON text: call content, such as the passages a search found) and,
    when it failed, what failed (`failure`, such as `timeout at search`: no call content)."""

    ok: bool
    ms: float = Field(ge=0, allow_inf_nan=False)
    result: str = ""
    failure: str | None = None


class ConfirmationRequested(_TurnEvent):
    """The read-back of `action` began to play in the reply to the turn; `draft` is the draft
    it reads back, as the JSON text the yes rule's receipt holds (call content)."""

    action: str = Field(min_length=1)
    draft: str = ""


class ConfirmationAnswered(_TurnEvent):
    """The yes rule read the turn as `decision` on `action`'s read-back, `by` its lists
    (`words`), or by a chat model's word on words they left unplaced, within its rails (`model`,
    D-082)."""

    action: str = Field(min_length=1)
    decision: ConfirmationDecision
    by: Literal["words", "model"] = "words"


class ActionCompleted(Event):
    """`action`'s write returned and was recorded, by its `request_id`; `result` is the write's
    real result as JSON text, as the call's record holds it (a ticket's number, say)."""

    action: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    result: str = ""


class ActionUnconfirmed(Event):
    """`action`'s write did not end in a record: `kind` says how it ended."""

    action: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    kind: UnconfirmedKind


class GuardBlocked(_TurnEvent):
    """The output guard blocked a clause of the reply to the turn, never spoken, for `reason`
    (the design's 8.2); a fixed phrase was said in its place."""

    reason: GuardReason


class TurnMetrics(TurnTimes, _TurnEvent):
    """How long a turn's steps took (its `TurnTimes`), and each model's usage in the call so far,
    as the turn settled (`usage`: the call's report holds its last)."""

    usage: tuple[ModelUsage, ...] = ()


# The events a call emits, in the order the design's 6.6 lists them.
EVENTS: tuple[type[Event], ...] = (
    CallStarted,
    CallEnded,
    UserTurnEnded,
    Interrupted,
    AgentSpeechEnded,
    ToolStarted,
    ToolFinished,
    ConfirmationRequested,
    ConfirmationAnswered,
    ActionCompleted,
    ActionUnconfirmed,
    GuardBlocked,
    ProviderFailed,
    TransportFailed,
    TurnMetrics,
)
