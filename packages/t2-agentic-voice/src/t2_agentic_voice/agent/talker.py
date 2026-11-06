"""The talker as the voice session sees it (plan 006): one turn in, a stream of events out, run in
the reply's cancel scope.

**In:** a `TalkerTurn` (core/conversation.py), which the session builds from its heard history:
the turn's heard words, whole, the language its transcript was heard in, the reply it was said
over and the reply it cut, and the call so far as the caller heard it, clause by clause (an
unplayed clause never reaches the model as said; a cut one is marked cut, with its share). The
talker of one call is built for it (`TalkerCall`: the call's id, its verified caller, its
language) and may keep what the history does not hold, its own tool results, between turns.

**Out:** events the session plays in order, as they come: a clause to speak (`SpokenClause`, in
its language, each whole once the model has written it, so the first is spoken while the model
still writes); a card to show (`ShownCard`); a tool begun and ended (`ToolBegan`, `ToolEnded`);
a progress line due, when a tool runs past its progress time (`ProgressDue`, spoken from the
phrase cache); a clause the output guard blocked (`ClauseBlocked`, never spoken: the session
speaks the fixed phrase, emits `GuardBlocked` and the talker keeps a developer note); each model
request as it goes and as it ends (`ModelRequested`, `ModelReplied`, for the call's usage and
the turn's times); and the reply's end (`ReplyDone`), after its last clause and its work.

**The scope** (D-060). The session iterates `Talker.reply` in a task it starts in the reply's
cancel scope (voice/session/scope.py's `CancelScope`, which `ReplyScope` describes), so a stop
cancels the model's request, the search and the speech at once. Work the talker runs beside the
stream (a tool) starts in the same scope, but for a tool whose barge-in is `finish`. A cancel
ends the stream at once, with no `ReplyDone`.

What `ChatTalker` does is plan 006's Track B (the loop: at most three model requests a turn,
tool results framed as data, the guard on every clause, the reply in the caller's language);
this module holds its shapes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel, Usage
from t2_agentic_voice.domain.talker_declaration import ProgressKey


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpokenClause(_Event):
    """A clause to speak, whole, in `language`: within the voice's `max_chars`, checked by the
    output guard."""

    text: str = Field(min_length=1)
    language: LanguageTag


class ShownCard(_Event):
    """A card to show the caller, its text checked by the output guard."""

    card: Card


class ToolBegan(_Event):
    """A tool call began: the model's id for the call, and the tool's name."""

    call_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)


class ToolEnded(_Event):
    """A tool call ended, whether it succeeded (`ok`: a `ToolError`, any other failure or the
    timeout is not), and how long it ran."""

    call_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    ok: bool
    ms: float = Field(ge=0, allow_inf_nan=False)


class ProgressDue(_Event):
    """A tool ran past its progress time: its progress line `key`, to speak in `language` from
    the phrase cache."""

    tool: str = Field(min_length=1)
    key: ProgressKey
    language: LanguageTag


class ClauseBlocked(_Event):
    """A clause the output guard blocked (rule B, domain/guard.py), never spoken: its `text`
    and `language`, and the ID-shaped tokens it held with no evidence, for the developer note
    and the trace, never for the caller."""

    text: str
    language: LanguageTag
    unsupported: tuple[str, ...] = ()


class ModelRequested(_Event):
    """A request to `model` went: counted in the call's usage, answered or not."""

    model: str = Field(min_length=1)


class ModelReplied(_Event):
    """A request to `model` ended: its `usage`, when the provider reported one, and the time
    from the request to its first token (`first_token_s`), None when none came."""

    model: str = Field(min_length=1)
    usage: Usage | None = None
    first_token_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ReplyDone(_Event):
    """The reply ended: its last clause given and its work done."""


type TalkerEvent = (
    SpokenClause
    | ShownCard
    | ToolBegan
    | ToolEnded
    | ProgressDue
    | ClauseBlocked
    | ModelRequested
    | ModelReplied
    | ReplyDone
)


class TalkerCall(_Event):
    """The call a talker is built for: its id, its verified caller, and its language, fixed at
    join (`VoiceAgent.call_language`)."""

    call_id: CallId
    caller: Caller
    language: LanguageTag


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


class Talker(Protocol):
    """One call's talker, as the session calls it (the module's docstring)."""

    def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        """The reply to `turn`, event by event, ending with `ReplyDone` unless cancelled."""
        ...


class ChatTalker:
    """The library's talker for one call (`call`): `agent`'s instructions and tools, the chat
    `model` and the tool `runner` the api layer injects, and the `settings` (`llm`, `guard`,
    `words.vocabulary`). A `Talker`."""

    def __init__(
        self,
        agent: VoiceAgent,
        *,
        model: ChatModel,
        runner: ToolRunner,
        settings: VoiceSettings,
        call: TalkerCall,
    ) -> None:
        self.agent, self.model, self.runner = agent, model, runner
        self.settings, self.call = settings, call

    def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        """The reply to `turn` (the module's docstring)."""
        raise NotImplementedError("the talker's loop is plan 006's Track B")
