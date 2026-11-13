"""What a call reports to the team's code: its events and, when it ends, its `CallReport` (the
design's 6.6; the report's models are core/call_report.py's, re-exported here, as are the
numbers that name a call's parts, core/ids.py's). Types every layer shares (ARCHITECTURE.md,
"Conventions"): `voice` builds them, `api` hands them to the observers a team registers, and an
app reads them through the `events` facade. Provisional.

Every event is frozen, from a closed list (`EVENTS`), and carries the call's ID, its turn's
(None for an event of the whole call) and when it happened. Observers run off the call's path
and cannot change it. The session emits every one: the talker's (a tool call begun and ended,
a clause the output guard blocked) and the actions' (a read-back requested and answered, a
write completed or unconfirmed, built from the outcome the action runner returns) among them;
the design's `Busy` comes with what it reports.

An event and the report hold what was heard and said (a tool's arguments and result, a
read-back's draft and a write's result among it), so neither is ever logged (call content is
logged at no level, docs/SECURITY.md, invariant 8); the report's numbers are written apart, with
no text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from t2_agentic_voice.core.call_report import CallReport as CallReport
from t2_agentic_voice.core.call_report import CandidateType as CandidateType
from t2_agentic_voice.core.call_report import ClientConnection as ClientConnection
from t2_agentic_voice.core.call_report import EndReason as EndReason
from t2_agentic_voice.core.call_report import LanguageBy as LanguageBy
from t2_agentic_voice.core.call_report import ModelUsage as ModelUsage
from t2_agentic_voice.core.call_report import RelayProtocol as RelayProtocol
from t2_agentic_voice.core.call_report import TurnRecord as TurnRecord
from t2_agentic_voice.core.call_report import TurnTimes as TurnTimes
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.ids import CALL_ID_PATTERN as CALL_ID_PATTERN
from t2_agentic_voice.core.ids import MAX_INDEX as MAX_INDEX
from t2_agentic_voice.core.ids import MAX_MS as MAX_MS
from t2_agentic_voice.core.ids import CallId as CallId
from t2_agentic_voice.core.ids import ClauseIndex as ClauseIndex
from t2_agentic_voice.core.ids import ReplyId as ReplyId
from t2_agentic_voice.core.ids import TurnId as TurnId
from t2_agentic_voice.core.yes_inputs import ActionName

# How an interruption ended the agent's speech (the design's 6.6): `stop`, the Stop button, Esc
# or a stop word; or the interruption rule's `correction` or `new_words` (domain/interruptions.py,
# whose verdict is `false` when the reply goes on).
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


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


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
    """A provider (speech-to-text, the chat model, text-to-speech) failed a request of the call,
    `kind` from `ProviderError`'s closed list."""

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

    action: ActionName
    draft: str = ""


class ConfirmationAnswered(_TurnEvent):
    """The yes rule read the turn as `decision` on `action`'s read-back, `by` its lists
    (`words`), or by a chat model's word on words they left unplaced, within its rails (`model`,
    D-082)."""

    action: ActionName
    decision: ConfirmationDecision
    by: Literal["words", "model"] = "words"


class ActionCompleted(Event):
    """`action`'s write returned and was recorded, by its `request_id`; `result` is the write's
    real result as JSON text, as the call's record holds it (a ticket's number, say)."""

    action: ActionName
    request_id: str = Field(min_length=1)
    result: str = ""


class ActionUnconfirmed(Event):
    """`action`'s write did not end in a record: `kind` says how it ended."""

    action: ActionName
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
