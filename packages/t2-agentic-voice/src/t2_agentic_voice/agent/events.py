"""What the talker streams to the session (agent/talker.py, which re-exports every name here, so
the session imports them from there): a clause to speak, a card to show, a tool begun and
ended, a progress line due, a clause the output guard blocked, an action's read-back to say,
each model request as it goes and as it ends, and the reply's end; and the reply's cancel scope,
which the talker starts its work in. They live apart from the talker so that the loop
(agent/turn.py) and the talker (agent/talker.py) both import them, and neither the other.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.events import GuardReason
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.domain.talker_declaration import ProgressKey


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpokenClause(_Event):
    """A clause to speak, whole, in `language`, checked by the output guard. Cut by the clause
    splitter with no length limit: the session fits it to the voice's `max_chars`, after the
    speaking rules have said its digits (agent/talker.py's docstring)."""

    text: str = Field(min_length=1)
    language: LanguageTag


class ShownCard(_Event):
    """A card to show the caller, its text checked by the output guard."""

    card: Card


class ToolBegan(_Event):
    """A tool call began: the model's id for the call, the tool's name, and the arguments the
    model wrote, for the call's trace (D-079)."""

    call_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    arguments: str = Field(default="", repr=False)


class ToolEnded(_Event):
    """A tool call ended, whether it succeeded (`ok`: a `ToolError`, any other failure or the
    timeout is not), how long it ran, what failed (`ToolResult.failure`), and what the tool gave
    back as JSON, for the call's trace (D-079)."""

    call_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    ok: bool
    ms: float = Field(ge=0, allow_inf_nan=False)
    failure: str | None = None
    result: str = Field(default="", repr=False)


class ProgressDue(_Event):
    """A tool with a progress line began: its line `key`, to say in `language` from the phrase
    cache `after_s` after the caller stopped speaking, unless the answer has begun by then; with
    `after_s` 0, at once."""

    tool: str = Field(min_length=1)
    key: ProgressKey
    language: LanguageTag
    after_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)


class ClauseBlocked(_Event):
    """A clause the output guard blocked (domain/guard.py, domain/claims.py), never spoken: its
    `text` and `language`, why (`reason`), and the ID-shaped tokens it held with no evidence, for
    the developer note and the trace, never for the caller."""

    text: str
    language: LanguageTag
    unsupported: tuple[str, ...] = ()
    reason: GuardReason = "unsupported_id"


class ReadBackRequested(_Event):
    """The talker called an action and its draft parsed: `plan` is what to read back. The
    session starts confirming when this plays, not when it is emitted, so an early start
    cancelled before then leaves nothing."""

    plan: ReadBackPlan


class ModelRequested(_Event):
    """A request to `model` went: counted in the call's usage, answered or not."""

    model: str = Field(min_length=1)


class ModelReplied(_Event):
    """A request to `model` ended: its `usage`, when the provider reported one, the time from
    the request to its first token (`first_token_s`), None when none came, and how many
    characters of its answer the stray-script filter took out or rewrote (`stray_characters`,
    agent/stray_script.py), with a label for each kind (`stray_scripts`), never a character."""

    model: str = Field(min_length=1)
    usage: Usage | None = None
    first_token_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stray_characters: int = Field(default=0, ge=0)
    stray_scripts: tuple[str, ...] = ()


class ReplyDone(_Event):
    """The reply ended: its last clause given and its work done; `unsaid_clauses`, how many
    clauses the talker wrote that the reply did not say, once it stopped before a question past
    its limit (agent/question_limit.py), 0 when it did not."""

    unsaid_clauses: int = Field(default=0, ge=0)


type TalkerEvent = (
    SpokenClause
    | ShownCard
    | ToolBegan
    | ToolEnded
    | ProgressDue
    | ClauseBlocked
    | ReadBackRequested
    | ModelRequested
    | ModelReplied
    | ReplyDone
)


class ReplyScope(Protocol):
    """What the talker starts its work in: the reply's cancel scope (voice/session/scope.py's
    `CancelScope` meets it)."""

    def start[T](self, work: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
        """Run `work` as a task of the scope, cancelled with the reply."""
        ...

    @property
    def cancelled(self) -> bool:
        """Whether the reply's scope has been cancelled."""
        ...
