"""How each of the talker's events plays in its reply (plan 006), for voice/session/talking.py,
which keeps each reply of the talker's as a `Talk` and plays each event its talker gives, one
step of the session's at a time, with a `TalkPlayer` (`play`): the events, and what each does,
are talking.py's module docstring's "Its events, in order". A reply that fails is told so once
at most (`tell`): the `error` notice when none of it was said, else `cut_off` after a beat. An
action's read-back (`ReadBackRequested`) starts confirming as it plays, never as it is written,
so an early start or a kept reply let go before then leaves nothing (read_back.py); it counts as
said, so no `error` notice follows a reply that only read back.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ProgressDue,
    ReplyDone,
    ShownCard,
    SpokenClause,
    TalkerEvent,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.events import GuardBlocked, ToolFinished, ToolStarted, TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing_tts import CallTrace
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.usage import Usage

# A step of the session's, run under its lock (call.py's `_guarded`).
Guarded = Callable[[str, Callable[[], Awaitable[None]]], Awaitable[None]]


@dataclass(kw_only=True)
class Talk:
    """One reply of the talker's as the session plays it: the turn and words it answers, its
    scope, its reply once opened (None while the early start holds it), the newer turns it is
    kept behind (`kept_for`: talking.py's kept reply), what was given while held or kept
    (`pending`), whether the talker's stream ended and how (`written`, `failure`), the clauses
    said, whether the guard's line was said, when its last model request went, whether the
    early start began it (`early`), the language it is said in (its last clause's, else its
    turn's), and the wait for its progress line (`waiting`: talking.py's progress line)."""

    turn_id: TurnId
    words: str
    scope: CancelScope
    early: bool = False
    reply: OpenReply | None = None
    kept_for: set[TurnId] = field(default_factory=set)
    pending: list[tuple[TalkerEvent, float]] = field(default_factory=list)
    written: bool = False
    failure: Exception | None = None
    said: int = 0
    told: bool = False
    request_at: float | None = None
    language: LanguageTag | None = None
    task: asyncio.Task[None] | None = None
    waiting: asyncio.Task[None] | None = None

    @property
    def held(self) -> bool:
        """Whether what its talker gives is kept, not played: its reply not yet opened (the
        early start's hold), or kept behind a newer turn."""
        return self.reply is None or bool(self.kept_for)


class TalkPlayer:
    """Plays the talker's events of one call (`setup`), its model requests counted in `usage`,
    its first token timed on the turns `turns` keeps, its tool calls traced on `trace`, and its
    actions' read-backs said in the call's `confirming` state."""

    def __init__(
        self,
        setup: CallSetup,
        usage: Usage,
        turns: TurnBook,
        trace: CallTrace,
        confirming: Confirming,
    ) -> None:
        self._setup, self._usage, self._turns, self._trace = setup, usage, turns, trace
        self._confirming = confirming

    async def tell(self, talk: Talk, reply: OpenReply, at: float) -> None:
        """The caller told the reply failed, once a reply, in its language (its last clause's,
        else its turn's)."""
        await self._told(talk, reply, talk.language or self._setup.language.tag, at)

    async def _told(self, talk: Talk, reply: OpenReply, tag: LanguageTag, at: float) -> None:
        if not talk.told:
            talk.told = True
            language = language_of(self._setup, tag)
            line = language.notices["cut_off" if talk.said else "error"]
            await reply.add_phrase(line, language=language.tag, at=at, beat_before=talk.said > 0)

    async def play(self, talk: Talk, event: TalkerEvent, at: float) -> None:
        """Play one of the talker's events in `talk`'s reply, given at `at` (talking.py's
        list); nothing while its reply is not open."""
        reply, turn_id = talk.reply, talk.turn_id
        if reply is None:
            return
        wall = self._setup.clock.wall()
        call_id, emit = self._setup.call_id, self._setup.emit
        match event:
            case SpokenClause(text=text, language=tag):
                talk.said, talk.language = talk.said + 1, tag
                await reply.add_clause(text, language=tag, at=at)
            case ShownCard(card=card):
                await reply.card(card)
            case ToolBegan(call_id=tool_call, tool=tool, arguments=arguments):
                self._trace.tool_began(turn_id, tool_call, tool=tool, arguments=arguments)
                started = ToolStarted(
                    call_id=call_id, turn_id=turn_id, at=wall, tool=tool, tool_call_id=tool_call
                )
                emit(started)
            case ToolEnded(
                call_id=tool_call, tool=tool, ok=ok, ms=ms, failure=failure, result=result
            ):
                self._trace.tool_ended(tool_call, ok=ok, failure=failure, result=result)
                finished = ToolFinished(
                    call_id=call_id,
                    turn_id=turn_id,
                    at=wall,
                    tool=tool,
                    tool_call_id=tool_call,
                    ok=ok,
                    ms=ms,
                )
                emit(finished)
            case ProgressDue(key=key, language=tag):
                progress = language_of(self._setup, tag).progress.get(key)
                if progress is not None:
                    await reply.add_phrase(progress, language=tag, at=at, progress=True)
            case ClauseBlocked(language=tag):
                emit(
                    GuardBlocked(call_id=call_id, turn_id=turn_id, at=wall, reason="unsupported_id")
                )
                await self._told(talk, reply, tag, at)
            case ReadBackRequested(plan=plan):  # its lines are templates: said, never guarded
                talk.said, talk.language = talk.said + 1, plan.language
                await self._confirming.read(reply, plan, at)
            case ModelRequested(model=model):
                self._usage.chat_requested(model)
                talk.request_at = at
            case ModelReplied(model=model, usage=usage, first_token_s=first):
                self._usage.chat_replied(model, usage)
                log = self._turns.turn(turn_id)
                asked = talk.request_at
                if log.first_token_at is None and first is not None and asked is not None:
                    log.first_token_at = asked + first
            case ReplyDone():
                if not talk.said:  # an empty answer, or one cut before a word: never silence
                    await self.tell(talk, reply, at)
                await reply.finish(at)
