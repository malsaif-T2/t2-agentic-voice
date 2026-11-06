"""The talker in the call (plan 006): how one call's session answers a turn with its talker
(agent/talker.py's `Talker`, the call's `CallSetup.talker`) instead of the echo, for
voice/session/call.py.

- **One reply, one scope** (D-060; "What voice-first means here", item 7). Each answer is the
  talker's reply to one `TalkerTurn`, built from the heard history (history.py's
  `conversation`: what the caller heard, clause by clause). The reply is opened on the speaker
  before its first clause (`Speaker.open_reply`, open_reply.py), and the talker runs in its
  cancel scope, on a task the scope holds, so a stop or the call's end cancels the model's
  request, the search and the speech at once. A turn answered while a reply to an earlier turn is
  in progress (said while the agent was silent, or while a search ran with nothing playing) stops
  that reply first, its work cancelled, so the talker starts again with both turns, the earlier
  one in the history as it ended (`rolled_back` when none of its reply played).
- **Its events, in order** (agent/talker.py): a clause is said (`SpokenClause`, in its language,
  open_reply.py's speech); a card is shown (`ShownCard`, `t2v/1`'s `card`); a tool's start and
  end are the public `ToolStarted` and `ToolFinished`, and while the talker or a tool works with
  nothing left to play the agent is `thinking` (playback.py); a progress line due is said from
  the phrase cache in its language (`ProgressDue`, timed apart); a clause the guard blocked is
  never said (`ClauseBlocked`): the call language's preset `error` notice is said in its place,
  once a reply, and `GuardBlocked` goes out (the talker keeps its developer note: the history
  holds only what the caller heard); each model request is counted in the call's usage as it
  goes and its tokens as it ends (`ModelRequested`, `ModelReplied`; an early start's, dropped
  unplayed, once it is let go), the first one's first token the turn's; and the reply is
  closed once it is done (`ReplyDone`). A talker that fails is logged by its failure's kind
  alone, a provider's failure told (`ProviderFailed`), and the caller hears the `error` notice,
  once a reply, after any clause already said too, in the turn's reply language (its last
  clause's, else the turn's as agent/language.py reads it); the reply is closed.
- **The early start** (plan 006, Q2; io.py's early start). A turn's `held` transcript starts the
  talker at once, in a scope of its own, while the hold runs: what it gives is kept, and nothing
  is asked for. Speech that resumes in the hold cancels it (`resumed`). When the hold ends (the
  turn's `TurnClosed`), the reply is opened in that scope (`release`), what was kept is played
  in order, each event guarded as one the talker gives later (a failure logged, the rest still
  played, the reply closed), and the rest as it comes; the turn's own transcript then finds it
  answering. Once the call has ended or is ending (its `ended` notice) nothing kept plays: the
  work is cancelled. A client's `stop` in the hold cancels the work too (`stopped`), and the
  turn is answered by nothing (`rolled_back`: the reply it began was stopped before any
  played).

Every event the talker gives is played as one step of the session's (`guarded`, under its lock,
in the order they came), so it never interleaves with one the Pipecat side hands; the client is
told what the agent is doing after each (`sync`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial

from t2_agentic_voice.agent.language import reply_language
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ProgressDue,
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
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.heard import HeardWords
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)
# A step of the session's, run under its lock (call.py's `_guarded`).
Guarded = Callable[[str, Callable[[], Awaitable[None]]], Awaitable[None]]
# The longest language name a `TalkerTurn` takes (core/conversation.py).
_LANGUAGE_CHARS = range(2, 17)


@dataclass(kw_only=True)
class _Talk:
    """One reply of the talker's as the session plays it: the turn and words it answers, its
    scope, its reply once opened (None while the early start holds it), what was given while
    held, whether the talker's stream ended and how (`written`, `failure`), the clauses said,
    whether the guard's line was said, when its last model request went, whether the early
    start began it (`early`), and the language it is said in (its last clause's, else its
    turn's)."""

    turn_id: TurnId
    words: str
    scope: CancelScope
    early: bool = False
    reply: OpenReply | None = None
    pending: list[tuple[TalkerEvent, float]] = field(default_factory=list)
    written: bool = False
    failure: Exception | None = None
    said: int = 0
    told: bool = False
    request_at: float | None = None
    language: LanguageTag | None = None
    task: asyncio.Task[None] | None = None


class Talking:
    """One call's talker replies, played by `speaker` for the turns `turns` keeps, each event
    played as a step `guarded` runs, the client's state brought up to date by `sync`; `over`
    says whether the call has ended or is ending."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        talker: Talker,
        speaker: Speaker,
        turns: TurnBook,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        over: Callable[[], bool],
    ) -> None:
        self._setup, self._talker, self._speaker, self._turns = setup, talker, speaker, turns
        self._usage, self._events, self._history = books.usage, books.events, books.history
        self._guarded, self._sync, self._over = guarded, sync, over
        self._clock = setup.clock
        self._talks: dict[TurnId, _Talk] = {}
        self._holding: set[TurnId] = set()  # the turns whose hold began and has not resumed

    async def answer(self, turn: TurnLog, heard: HeardWords, at: float) -> None:
        """Answer `turn`, its words `heard`, with the talker, unless its early start answers it
        already (the same words); the replies in progress to earlier turns stopped first."""
        talk = self._talks.get(turn.turn_id)
        if talk is not None and talk.reply is None and talk.scope.cancelled:  # stopped in the hold
            self._turns.ended(turn, "rolled_back")
            return
        if talk is not None and talk.early and talk.words == heard.text:
            if talk.reply is None:
                await self.release(turn, at)
            return
        if talk is not None:
            await self._dropped(talk)
            if talk.reply is not None:  # its reply said other words: stopped
                await self._speaker.stop(at, client=False)
        await self._stop_earlier(turn, at)
        handed = self._turn(turn, heard)
        reply = await self._speaker.open_reply(at, turn_id=turn.turn_id)
        turn.reply_id = reply.reply_id
        talk = _Talk(turn_id=turn.turn_id, words=heard.text, scope=reply.scope, reply=reply)
        self._start(talk, handed)

    def hold_began(self, turn_id: TurnId) -> None:
        """Smart Turn called the turn complete: its `held` transcript may start the talker."""
        self._holding.add(turn_id)

    async def held(self, turn: TurnLog, heard: HeardWords) -> None:
        """The turn's `held` transcript came while its hold runs: the talker starts on it, its
        events kept until the hold ends (the module's early start)."""
        if turn.turn_id not in self._holding or turn.turn_id in self._talks:
            return
        scope = CancelScope(name=f"held-{turn.turn_id}", clock=self._clock)
        talk = _Talk(turn_id=turn.turn_id, words=heard.text, scope=scope, early=True)
        self._start(talk, self._turn(turn, heard))

    async def resumed(self, turn_id: TurnId) -> None:
        """The caller spoke again within the turn's hold: what its early start began is
        cancelled, and the turn goes on."""
        self._holding.discard(turn_id)
        talk = self._talks.get(turn_id)
        if talk is not None and talk.reply is None:
            await self._dropped(talk)

    async def release(self, turn: TurnLog, at: float) -> None:
        """The turn's hold ended (its `TurnClosed`): the reply its early start wrote is opened
        in its scope, what it kept played in order, and closed when its talker is done."""
        self._holding.discard(turn.turn_id)
        talk = self._talks.get(turn.turn_id)
        if talk is None or talk.reply is not None or talk.scope.cancelled:
            return
        if self._over():  # the call has ended, or its `ended` notice plays: nothing kept plays
            await self._dropped(talk)
            return
        await self._stop_earlier(turn, at)
        talk.reply = await self._speaker.open_reply(at, turn_id=turn.turn_id, scope=talk.scope)
        turn.reply_id = talk.reply.reply_id
        while talk.pending:
            event, when = talk.pending.pop(0)
            await self._held_event(talk, event, when)
        if talk.written:
            await self._close(talk, talk.failure)

    async def stopped(self) -> None:
        """The client's `stop`: the work of every early start still held is cancelled, so
        nothing it kept plays, and its turn is answered by nothing (`answer`)."""
        for talk in [talk for talk in self._talks.values() if talk.reply is None]:
            await self._cancel(talk)

    async def end(self) -> None:
        """The call ended: every early start still held is cancelled (a reply's own scope is
        cancelled with the reply)."""
        for talk in [talk for talk in self._talks.values() if talk.reply is None]:
            await self._dropped(talk)

    def _turn(self, turn: TurnLog, heard: HeardWords) -> TalkerTurn:
        """The turn as the talker reads it: its words whole, the language they were heard in,
        the replies it spoke over and cut, and the call before it as the caller heard it."""
        language = heard.language
        if language is not None and len(language) not in _LANGUAGE_CHARS:
            language = None
        return TalkerTurn(
            turn_id=turn.turn_id,
            words=heard.text,
            language=language,
            over_reply=turn.over_reply,
            cut_reply=turn.cut_reply,
            conversation=self._history.conversation(before=turn.turn_id),
        )

    def _start(self, talk: _Talk, turn: TalkerTurn) -> None:
        spoken = [language.tag for language in self._setup.agent.languages]
        talk.language = reply_language(turn, call=self._setup.language.tag, spoken=spoken)
        self._talks[talk.turn_id] = talk
        talk.task = talk.scope.start(self._run(talk, turn), name=f"talker-{talk.turn_id}")

    async def _dropped(self, talk: _Talk) -> None:
        """`talk` is let go: its work cancelled (its reply, if opened, stopped by whoever
        dropped it)."""
        if self._talks.get(talk.turn_id) is talk:
            del self._talks[talk.turn_id]
        await self._cancel(talk)

    async def _cancel(self, talk: _Talk) -> None:
        """`talk`'s work cancelled; the model requests it made while held, which went though
        none of it will play, counted in the call's usage (usage.py) as they would have been."""
        await talk.scope.cancel()
        for event, _ in talk.pending:
            if isinstance(event, ModelRequested):
                self._usage.chat_requested(event.model)
            elif isinstance(event, ModelReplied):
                self._usage.chat_replied(event.model, event.usage)
        talk.pending.clear()

    async def _stop_earlier(self, turn: TurnLog, at: float) -> None:
        """Before `turn` is answered: the replies in progress to earlier turns stopped, their
        work cancelled, with one `Interrupted`; none when one answers this turn or a later
        one."""
        playback = self._speaker.playback
        answering = [r for r in playback.in_progress() if r.turn_id is not None]
        if not answering or max(r.turn_id or 0 for r in answering) >= turn.turn_id:
            return
        newest = answering[-1]
        await self._speaker.stop(at, client=False)
        turn.cut_reply = turn.cut_reply if turn.cut_reply is not None else newest.reply_id
        self._events.interrupted(newest.turn_id, "new_words")

    async def _run(self, talk: _Talk, turn: TalkerTurn) -> None:
        """Iterate the talker's reply in `talk`'s scope, each event kept while held, else
        played as a step of the session's; then the reply closed. The talker's stream is closed
        here, in the reply's scope, even when a cancel comes while an event of it waits (D-060),
        so the model's request never ends later, in the event loop's finalizer."""
        failure: Exception | None = None
        stream = self._talker.reply(turn, scope=talk.scope)
        try:
            async for event in stream:
                at = self._clock.now()
                if talk.reply is None:
                    talk.pending.append((event, at))
                else:
                    await self._guarded("talker_event", partial(self._play, talk, event, at))
        except Exception as error:  # the talker's failure: told, and the reply closed
            failure = error
        finally:
            close = getattr(stream, "aclose", None)  # an async generator's, as a talker's is
            if close is not None:
                await close()
        if talk.reply is None:
            talk.written, talk.failure = True, failure
            return
        await self._guarded("talker_end", partial(self._close, talk, failure))

    async def _held_event(self, talk: _Talk, event: TalkerEvent, at: float) -> None:
        """Play one event the hold kept, guarded as a step of the session's is (`_run`'s): a
        failure logged by its kind alone, so the rest still plays and the reply closes."""
        try:
            await self._play(talk, event, at)
        except Exception as error:
            failure = type(error).__qualname__
            call_id = self._setup.call_id
            _log.error("session_step_failed", call_id=call_id, step="talker_event", failure=failure)

    async def _close(self, talk: _Talk, failure: Exception | None) -> None:
        reply = talk.reply
        if reply is None:
            return
        now = self._clock.now()
        if failure is not None:
            kind = type(failure).__qualname__
            _log.warning("talker_failed", call_id=self._setup.call_id, failure=kind)
            if isinstance(failure, ProviderError):
                self._events.failed(failure.kind, failure.retryable, talk.turn_id)
            if not talk.told:  # in the reply's language, after its clauses too
                talk.told = True
                language = language_of(self._setup, talk.language or self._setup.language.tag)
                await reply.add_phrase(language.notices["error"], language=language.tag, at=now)
        await reply.finish(now)
        await self._sync()

    async def _play(self, talk: _Talk, event: TalkerEvent, at: float) -> None:
        """Play one of the talker's events (the module's list), given at `at`."""
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
            case ToolBegan(call_id=tool_call, tool=tool):
                started = ToolStarted(
                    call_id=call_id, turn_id=turn_id, at=wall, tool=tool, tool_call_id=tool_call
                )
                emit(started)
            case ToolEnded(call_id=tool_call, tool=tool, ok=ok, ms=ms):
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
                if not talk.told:
                    talk.told = True
                    line = language_of(self._setup, tag).notices["error"]
                    await reply.add_phrase(line, language=tag, at=at)
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
                await reply.finish(at)
        await self._sync()
