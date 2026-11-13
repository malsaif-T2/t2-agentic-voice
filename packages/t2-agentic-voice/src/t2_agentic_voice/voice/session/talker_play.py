"""How each of the talker's replies runs and each of its events plays, for
voice/session/talking.py, which keeps each reply of the talker's as a `Talk`.

- **The run** (`TalkRunner`). The talker's reply to a turn is iterated in the reply's scope, each
  event kept while the reply is held or kept (talking.py's early start and kept reply), else
  played as one step of the session's (`guarded`, under its lock, in the order they came); what
  was kept is let out in order (`let_out`), each event guarded so a failure, logged by its kind
  alone, leaves the rest to play; and the reply is closed once its talker is done. The talker's
  stream is closed in the reply's scope, even when a cancel comes while an event of it waits
  (D-060), so the model's request never ends later, in the event loop's finalizer. A talker that
  fails is logged by its failure's kind alone, a provider's failure told (`ProviderFailed`), and
  the caller told (`tell`). Work let go (`cancel`) still counts the model requests it made while
  held or kept in the call's usage.
- **Each event** (`TalkPlayer.play`): the events, and what each does, are talking.py's module
  docstring's "Its events, in order". A reply that fails is told so once at most (`tell`): the
  `error` notice when none of it was said, else `cut_off` after a beat. An action's read-back
  (`ReadBackRequested`) starts confirming as it plays, never as it is written, so an early start
  or a kept reply let go before then leaves nothing (read_back.py); it counts as said, so no
  `error` notice follows a reply that only read back. What the stray-script filter took out of a
  model request's answer (`ModelReplied`'s count and labels) is added to its turn's log, for the
  turn's span, and logged by its count and labels alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial

from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ProgressDue,
    ReadBackRequested,
    ReplyDone,
    ShownCard,
    SpokenClause,
    Talker,
    TalkerEvent,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import GuardBlocked, ToolFinished, ToolStarted, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing_tts import CallTrace
from t2_agentic_voice.domain.text.scripts import MAX_LABELS
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.usage import Usage

_log = get_logger(__name__)
# Play one of the talker's events in its reply, given at a time (talking.py's `_play`).
Play = Callable[["Talk", TalkerEvent, float], Awaitable[None]]


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
        self._arguments: dict[str, str] = {}  # each tool call's under way, for its end's event

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
                self._arguments[tool_call] = arguments
                started = ToolStarted(
                    call_id=call_id,
                    turn_id=turn_id,
                    at=wall,
                    tool=tool,
                    tool_call_id=tool_call,
                    arguments=arguments,
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
                    arguments=self._arguments.pop(tool_call, ""),
                    ok=ok,
                    ms=ms,
                    result=result,
                    failure=failure,
                )
                emit(finished)
            case ProgressDue(key=key, language=tag):
                progress = language_of(self._setup, tag).progress.get(key)
                if progress is not None:
                    await reply.add_phrase(progress, language=tag, at=at, progress=True)
            case ClauseBlocked(language=tag, reason=reason):
                emit(GuardBlocked(call_id=call_id, turn_id=turn_id, at=wall, reason=reason))
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
                self._stray(log, event)
            case ReplyDone():
                if not talk.said:  # an empty answer, or one cut before a word: never silence
                    await self.tell(talk, reply, at)
                await reply.finish(at)

    def _stray(self, log: TurnLog, replied: ModelReplied) -> None:
        """What the stray-script filter took out of a model request's answer, added to its
        turn's log and logged by its count and labels alone, never a character or a word."""
        if not replied.stray_characters:
            return
        log.stray_characters += replied.stray_characters
        labels = sorted({*log.stray_scripts, *replied.stray_scripts})
        log.stray_scripts = tuple(labels[:MAX_LABELS])
        _log.info(
            "talker_stray_script_removed",
            call_id=self._setup.call_id,
            turn_id=log.turn_id,
            characters=replied.stray_characters,
            scripts=replied.stray_scripts,
        )


class TalkRunner:
    """Runs one call's talker replies (the module's run): `talker` writes each, each event is
    played by `play` as a step `guarded` runs, a failure is told by `player`, and the client
    is told what the agent is doing by `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        talker: Talker,
        player: TalkPlayer,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        play: Play,
    ) -> None:
        self._setup, self._clock, self._talker, self._player = setup, setup.clock, talker, player
        self._usage, self._events = books.usage, books.events
        self._guarded, self._sync, self._play = guarded, sync, play

    async def run(self, talk: Talk, turn: TalkerTurn) -> None:
        """Iterate the talker's reply to `turn` in `talk`'s scope, each event kept while held or
        kept, else played as a step of the session's; then the reply closed (the module's
        run)."""
        failure: Exception | None = None
        stream: AsyncIterator[TalkerEvent] | None = None
        try:
            stream = self._talker.reply(turn, scope=talk.scope)  # a team's may raise here
            async for event in stream:
                at = self._clock.now()
                if talk.held:
                    talk.pending.append((event, at))
                else:
                    await self._guarded("talker_event", partial(self._play, talk, event, at))
        except Exception as error:  # the talker's failure: told, and the reply closed
            failure = error
        finally:
            close = getattr(stream, "aclose", None)  # an async generator's, as a talker's is
            if close is not None:
                await close()
        if talk.held:
            talk.written, talk.failure = True, failure
            return
        await self._guarded("talker_end", partial(self._close, talk, failure))

    async def let_out(self, talk: Talk) -> None:
        """Play what `talk` kept, in order, each event guarded (`_held_event`), and close its
        reply when its talker is done."""
        while talk.pending:
            event, when = talk.pending.pop(0)
            await self._held_event(talk, event, when)
        if talk.written:
            await self._close(talk, talk.failure)

    async def cancel(self, talk: Talk) -> None:
        """`talk`'s work cancelled; the model requests it made while held or kept, which went
        though none of it will play, counted in the call's usage (usage.py) as they would have
        been."""
        await talk.scope.cancel()
        for event, _ in talk.pending:
            if isinstance(event, ModelRequested):
                self._usage.chat_requested(event.model)
            elif isinstance(event, ModelReplied):
                self._usage.chat_replied(event.model, event.usage)
        talk.pending.clear()

    async def _held_event(self, talk: Talk, event: TalkerEvent, at: float) -> None:
        """Play one event the hold kept, guarded as a step of the session's is (`run`'s): a
        failure logged by its kind alone, so the rest still plays and the reply closes."""
        try:
            await self._play(talk, event, at)
        except Exception as error:
            failure = type(error).__qualname__
            call_id = self._setup.call_id
            _log.error("session_step_failed", call_id=call_id, step="talker_event", failure=failure)

    async def _close(self, talk: Talk, failure: Exception | None) -> None:
        """Close `talk`'s reply, its talker done: a failure logged by its kind alone, a
        provider's told, and the caller told (`TalkPlayer.tell`), in its language, after its
        clauses too."""
        if talk.waiting is not None:
            talk.waiting.cancel()
        reply = talk.reply
        if reply is None:
            return
        now = self._clock.now()
        if failure is not None:
            kind = type(failure).__qualname__
            _log.warning("talker_failed", call_id=self._setup.call_id, failure=kind)
            if isinstance(failure, ProviderError):
                self._events.failed(failure.kind, failure.retryable, talk.turn_id)
            await self._player.tell(talk, reply, now)
        await reply.finish(now)
        await self._sync()
