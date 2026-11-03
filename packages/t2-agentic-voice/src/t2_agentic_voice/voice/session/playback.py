"""The agent's replies as they play, for one call's session (voice/session/call.py): which the
session has asked for, which are playing, how much of each played, and when each began and ended
(`Playback`; voice/session/io.py's replies, the drop rule and the stop path); and the `Speaker`,
which asks for each reply clause by clause, captions each clause as it plays, tells the caller
each notice, stops, and ends each reply, counted, traced and recorded.

A reply plays from its first clause's first audio (`ClauseQueued`) to its end: its last clause
played or failed, or a stop or the call's end that dropped what was left. The drop rule reads
those times: a turn whose speech began while a reply played, or within `DROP_AFTER_S` after one
ended, is not answered.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.tracing_tts import CallTrace, ReplyNumbers
from t2_agentic_voice.domain.declaration import NoticeKind
from t2_agentic_voice.voice.protocol import Caption, ClauseIndex, Notice, ReplyId, SessionMessage
from t2_agentic_voice.voice.session.commands import Send, StopSpeaking
from t2_agentic_voice.voice.session.echo import Line, fixed
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import CallEvents
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)
from t2_agentic_voice.voice.session.usage import Usage

# How long after a reply ends a turn's speech still counts as the agent's own voice, leaked past
# the browser's echo cancellation (plan 003's decision log): seconds.
DROP_AFTER_S = 0.3
# What a reply is: the greeting (reply 0), a turn's echo, or a spoken notice.
ReplyKind = Literal["greeting", "echo", "notice"]


@dataclass(kw_only=True)
class Clause:
    """One clause of a reply as it plays: its caption, the characters of the request it sent
    (none for a cached phrase), and what came of it."""

    caption: str
    characters: int
    cached: bool
    requested_at: float | None = None
    queued_at: float | None = None
    played: bool = False
    done: bool = False
    chunks: int = 0
    cut_short: bool = False


@dataclass(kw_only=True)
class Reply:
    """One of the agent's replies: its number, what it is, the caller's turn it answers (None
    for the greeting or a notice), the notice it speaks, its clauses, when it began and ended
    playing (`ended_at` set however it ended), whether a clause failed and the caller was told
    of it (`told`: one `error` notice a reply), and whether a stop dropped it."""

    reply_id: ReplyId
    kind: ReplyKind
    turn_id: TurnId | None = None
    notice: NoticeKind | None = None
    clauses: list[Clause] = field(default_factory=list)
    started_at: float | None = None
    ended_at: float | None = None
    failed: bool = False
    told: bool = False
    stopped: bool = False

    @property
    def text(self) -> str:
        """What the reply was to say: its clauses' captions, one after another."""
        return " ".join(clause.caption for clause in self.clauses)

    @property
    def played_fraction(self) -> float:
        """How much of the reply played whole, by its clauses' captions' characters: 1 when every
        clause played."""
        total = sum(len(clause.caption) for clause in self.clauses)
        played = sum(len(clause.caption) for clause in self.clauses if clause.played)
        return played / total if total else 1.0

    @property
    def first_audio_s(self) -> float | None:
        """From its first request to that request's first audio: none when no request's audio
        came."""
        for clause in self.clauses:
            if clause.requested_at is not None and clause.queued_at is not None:
                return max(0.0, clause.queued_at - clause.requested_at)
        return None

    def numbers(self) -> ReplyNumbers:
        """What it took, as its text-to-speech span records it: the requests that went (their
        characters), the chunks played, the phrases played from the cache."""
        asked = [clause for clause in self.clauses if clause.requested_at is not None]
        first = self.first_audio_s
        return ReplyNumbers(
            characters=sum(clause.characters for clause in asked),
            chunks=sum(clause.chunks for clause in self.clauses),
            requests=len(asked),
            cache_hits=sum(clause.cached for clause in self.clauses),
            first_audio_ms=None if first is None else first * 1000,
            cut_short=any(clause.cut_short for clause in self.clauses),
        )


class Playback:
    """Every reply of one call, by its number, the next numbered from 0."""

    def __init__(self) -> None:
        self._replies: dict[ReplyId, Reply] = {}

    @property
    def next_id(self) -> ReplyId:
        """The number the next reply takes."""
        return len(self._replies)

    def ask(
        self,
        kind: ReplyKind,
        lines: list[Line],
        *,
        turn_id: TurnId | None = None,
        notice: NoticeKind | None = None,
    ) -> Reply:
        """Keep the reply `lines` say, numbered `next_id`: each a cached phrase, or a request of
        its text's characters."""
        clauses = [
            Clause(
                caption=line.caption,
                characters=0 if line.speak.audio is not None else len(line.speak.text),
                cached=line.speak.audio is not None,
            )
            for line in lines
        ]
        reply = Reply(
            reply_id=self.next_id, kind=kind, turn_id=turn_id, notice=notice, clauses=clauses
        )
        self._replies[reply.reply_id] = reply
        return reply

    def reply(self, reply_id: ReplyId) -> Reply | None:
        return self._replies.get(reply_id)

    def clause(self, reply_id: ReplyId, index: ClauseIndex) -> tuple[Reply, Clause] | None:
        """The reply and its clause an event names, while the reply plays; None for any other."""
        reply = self._replies.get(reply_id)
        if reply is None or reply.ended_at is not None or index >= len(reply.clauses):
            return None
        return reply, reply.clauses[index]

    def requested(self, event: Synthesizing) -> Clause | None:
        """The clause whose request went, which `event` reports, its reply ended or not: the
        report of a request that went before the call's end still comes after it."""
        reply = self._replies.get(event.reply_id)
        if reply is None or event.clause >= len(reply.clauses):
            return None
        clause = reply.clauses[event.clause]
        clause.requested_at = event.at
        return clause

    def queued(self, event: ClauseQueued) -> tuple[Reply, Clause] | None:
        """The clause whose first audio `event` reports queued; its reply begins playing."""
        found = self.clause(event.reply_id, event.clause)
        if found is not None:
            reply, clause = found
            clause.queued_at = event.at
            if reply.started_at is None:
                reply.started_at = event.at
        return found

    def done(self, event: ClausePlayed | ClauseFailed) -> tuple[Reply, Clause] | None:
        """The clause `event` reports played whole or failed; its reply ends with its last."""
        found = self.clause(event.reply_id, event.clause)
        if found is None:
            return None
        reply, clause = found
        clause.done = True
        if isinstance(event, ClausePlayed):
            clause.played, clause.chunks, clause.cut_short = True, event.chunks, event.cut_short
        else:
            reply.failed = True
        if all(each.done for each in reply.clauses):
            reply.ended_at = event.at
        return found

    def in_progress(self) -> list[Reply]:
        """The replies asked for that have not ended, oldest first."""
        return [reply for reply in self._replies.values() if reply.ended_at is None]

    def drop(self, at: float) -> list[Reply]:
        """End at `at` every reply asked for that has not ended, as a stop or the call's end
        drops them; the replies dropped, oldest first."""
        dropped = self.in_progress()
        for reply in dropped:
            reply.ended_at = at
        return dropped

    @property
    def speaking(self) -> bool:
        """Whether a reply is playing: its first audio queued, and not ended."""
        return any(reply.started_at is not None for reply in self.in_progress())

    @property
    def waiting(self) -> bool:
        """Whether a reply asked for has no audio queued yet."""
        return any(reply.started_at is None for reply in self.in_progress())

    def heard_over(self, speech_at: float) -> bool:
        """Whether speech that began at `speech_at` began while a reply played, or within
        `DROP_AFTER_S` after one ended (the drop rule)."""
        for reply in self._replies.values():
            if reply.started_at is None or reply.started_at > speech_at:
                continue
            if reply.ended_at is None or speech_at <= reply.ended_at + DROP_AFTER_S:
                return True
        return False


class Speaker:
    """How one call's session speaks: each reply asked for clause by clause (`say`), each clause
    captioned as it plays, each notice told, a stop, and each reply's end, counted (`usage`),
    traced (`trace`) and recorded (`recorder`). When a reply ends, however, its
    `AgentSpeechEnded` goes out, its span ends, and the session hears of it (`ended`)."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        *,
        usage: Usage,
        trace: CallTrace,
        recorder: CallRecorder,
        events: CallEvents,
        ended: Callable[[Reply], Awaitable[None]],
    ) -> None:
        self.playback = Playback()
        self._setup, self._commands, self._ended = setup, commands, ended
        self._usage, self._trace, self._recorder, self._events = usage, trace, recorder, events
        self._tag = setup.language.tag
        self._voice = setup.settings.tts.languages[self._tag]

    async def send(self, message: SessionMessage) -> None:
        await self._commands.run(Send(message=message))

    async def say(
        self,
        kind: ReplyKind,
        lines: list[Line],
        at: float,
        *,
        turn_id: TurnId | None = None,
        notice: NoticeKind | None = None,
    ) -> Reply:
        """Ask for the reply `lines` say, clause by clause, its span opened."""
        reply = self.playback.ask(kind, lines, turn_id=turn_id, notice=notice)
        voice = self._voice
        self._trace.tts_started(
            reply.reply_id, turn_id, model=voice.model, voice=voice.voice, language=self._tag
        )
        for line in lines:
            if line.speak.audio is not None:
                self._usage.cached(self._tag)
            self._recorder.asked(at, line.speak, line.caption)
            await self._commands.run(line.speak)
        return reply

    async def notice(self, kind: NoticeKind, at: float) -> Reply | None:
        """Tell the caller the notice of `kind`: its `notice` message, then spoken from the
        phrase cache as the next reply (none when the cache does not hold it)."""
        text = self._setup.language.notices[kind]
        await self.send(Notice(kind=kind, text=text))
        line = fixed(self._setup, text, reply_id=self.playback.next_id)
        return None if line is None else await self.say("notice", [line], at, notice=kind)

    async def queued(self, event: ClauseQueued) -> Reply | None:
        """A clause's first audio was queued: its caption goes out (a notice shows as its
        `notice` message); the reply it belongs to, while it plays."""
        found = self.playback.queued(event)
        if found is None:
            return None
        reply, clause = found
        if reply.kind != "notice":
            caption = Caption(
                speaker="agent",
                text=clause.caption,
                final=True,
                turn_id=reply.turn_id,
                reply_id=reply.reply_id,
                clause=event.clause,
            )
            await self.send(caption)
        return reply

    async def done(self, event: ClausePlayed | ClauseFailed, *, tell: bool) -> None:
        """A clause played whole or failed; an echo's first failed clause gives the `error`
        notice when `tell`, and the reply ends with its last clause."""
        found = self.playback.done(event)
        if found is None:
            return
        reply = found[0]
        if isinstance(event, ClausePlayed):
            self._usage.played(self._tag, event)
        else:
            self._events.failed(event.failure, event.retryable, reply.turn_id)
            if reply.kind == "echo" and not reply.told and tell:
                reply.told = True
                await self.notice("error", event.at)
        if reply.ended_at is not None:
            await self._end(reply)

    async def stop(self, at: float) -> None:
        """Drop every reply asked for so far, naming the newest (`StopSpeaking`); each ends at
        once, stopped."""
        dropped = self.playback.in_progress()
        if not dropped:
            return
        await self._commands.run(StopSpeaking(reply_id=self.playback.next_id - 1))
        self._recorder.line(at, "stopped", replies=[reply.reply_id for reply in dropped])
        for reply in self.playback.drop(at):
            reply.stopped = True
            self._events.stopped(reply.turn_id)
            await self._end(reply)

    async def cut(self, at: float) -> None:
        """The call ended: every reply still asked for ends, as much of it played as did."""
        for reply in self.playback.drop(at):
            await self._end(reply)

    async def _end(self, reply: Reply) -> None:
        self._events.spoke(reply.turn_id, reply.text, reply.played_fraction)
        self._trace.tts_ended(reply.reply_id, reply.numbers())
        await self._ended(reply)
