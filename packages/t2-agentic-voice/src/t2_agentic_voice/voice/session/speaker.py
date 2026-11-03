"""How one call's session speaks (voice/session/call.py): the `Speaker` asks for each reply clause
by clause, captions each clause as it plays, tells the caller each notice, stops, and ends each
reply, counted, traced and recorded. The replies as they play are playback.py's (`Playback`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.tracing_tts import CallTrace
from t2_agentic_voice.domain.declaration import NoticeKind
from t2_agentic_voice.voice.protocol import CallState, Caption, Notice, SessionMessage, State
from t2_agentic_voice.voice.session.commands import Send, StopSpeaking
from t2_agentic_voice.voice.session.echo import Line, fixed
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.playback import Playback, Reply, ReplyKind
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import CallEvents
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)
from t2_agentic_voice.voice.session.usage import Usage


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
        self._state: CallState | None = None

    async def send(self, message: SessionMessage) -> None:
        await self._commands.run(Send(message=message))

    async def show_state(self, *, awaited: bool) -> None:
        """Tell the client what the agent is doing, when it changed: speaking while a reply
        plays; thinking while a reply asked for has no audio yet, or a turn's transcript is
        `awaited`; listening otherwise."""
        state: CallState = "listening"
        if self.playback.speaking:
            state = "speaking"
        elif self.playback.waiting or awaited:
            state = "thinking"
        if state != self._state:
            self._state = state
            await self.send(State(state=state))

    def synthesizing(self, event: Synthesizing) -> None:
        """A clause's request went, its reply ended or not (the report of a request that went
        before the call's end still comes after it): its characters counted."""
        clause = self.playback.requested(event)
        if clause is not None:
            self._usage.synthesizing(self._tag, clause.characters)

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
