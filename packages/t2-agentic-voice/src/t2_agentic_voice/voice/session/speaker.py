"""How one call's session speaks (voice/session/call.py): the `Speaker` asks for each reply clause
by clause, each in a cancel scope of its own (scope.py), captions each clause as it plays, tells
the caller each notice, stops, says the last reply again (each clause as it was sent, in its own
language, so a take the clause cache held is found again), and ends each reply, counted, traced,
recorded and kept in the heard history (history.py). The replies as they play: playback.py's.

What the caller heard of a clause a stop or the call's end cut is the agent's audio the output
sent since that clause began playing (its first audio queued, or the clause before it ended:
`AgentAudio` reaches the session in order with each clause's `ClausePlayed`, voice/transport.py's
`OutputTap`), over the clause's length, estimated from this call's clauses played so far, seconds
per caption character (`SECONDS_PER_CHARACTER` before any played), as a reply's share counts.

A reply's scope is cancelled once the reply ends, however, so a reply that will ask for more
clauses while its work runs (the talker's) must not end before that work is done: such a reply
is opened before its first clause, written clause by clause (`write`, each in the language the
talker wrote it in, counted under that language's model) and closed once its work is done
(`open_reply`, open_reply.py's `OpenReply`). Its scope may be one its work began in before it
was opened (the early start's, plan 006). An action's line is a reply of its own (`say_line`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import NoticeKind
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import (
    CallState,
    Caption,
    ClauseIndex,
    Notice,
    ReplyId,
    SessionHello,
    SessionMessage,
    ShowCard,
    State,
    Unduck,
)
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.commands import Send, Speak, StopSpeaking
from t2_agentic_voice.voice.session.echo import BEAT_S, Line, again, fixed, padded
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.open_reply import OpenReply
from t2_agentic_voice.voice.session.playback import (
    Clause,
    Playback,
    ReadBackPart,
    Reply,
    ReplyKind,
)
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)

# How long a clause's audio lasts per character of its caption until a clause of the call has
# played (the agent's estimate: about 14 characters a second, a calm speaking rate), for the share
# of a clause cut before any other played.
SECONDS_PER_CHARACTER = 0.07


class Speaker:
    """How one call's session speaks: each reply asked for clause by clause (`say`), in a cancel
    scope of its own (`scope`), each clause captioned as it plays, each notice told, a stop, a
    reply said again (`repeat`), and each reply's end, counted, traced, recorded and kept in
    the heard history (`books`). When a reply ends, however, its scope is cancelled, its
    `AgentSpeechEnded` goes out, its span ends, and the session hears of it (`ended`); and
    of any stop that dropped the replies in progress (`stopped`)."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        books: CallBooks,
        *,
        ended: Callable[[Reply], Awaitable[None]],
        stopped: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.playback = Playback()
        self._setup, self._commands, self._ended = setup, commands, ended
        self._stopped = stopped
        self._usage, self._trace, self._recorder = books.usage, books.trace, books.recorder
        self._events, self._history = books.events, books.history
        self._tag = setup.language.tag
        self._voice = setup.settings.tts.languages[self._tag]
        self._two_step = setup.settings.interruptions.mode == "two_step"
        self._state: CallState | None = None
        self._scopes: dict[int, CancelScope] = {}
        self._since_s = 0.0  # the agent's audio sent since the clause playing began
        self._played_s, self._played_chars = 0.0, 0  # the clauses played whole so far

    async def send(self, message: SessionMessage) -> None:
        await self._commands.run(Send(message=message))

    async def show_state(self, *, awaited: bool, confirming: bool = False) -> None:
        """Tell the client what the agent is doing, when it changed: speaking while a reply
        plays; while an action's read-back is `confirming` (read_back.py), confirming otherwise;
        thinking while a reply asked for has no audio yet, or a turn's transcript is `awaited`;
        listening otherwise."""
        state: CallState = "listening"
        if self.playback.speaking:
            state = "speaking"
        elif confirming:
            state = "confirming"
        elif self.playback.waiting or awaited:
            state = "thinking"
        if state != self._state:
            self._state = state
            await self.send(State(state=state))

    def synthesizing(self, event: Synthesizing) -> None:
        """A clause's request went, its reply ended or not (the report of a request that went
        before a stop or the call's end still comes after it: TD-055): its characters
        counted."""
        clause = self.playback.requested(event)
        if clause is not None:
            self._usage.synthesizing(clause.language or self._tag, clause.characters)

    def scope(self, reply_id: int) -> CancelScope:
        """The cancel scope of reply `reply_id`, which the work that answers its turn starts
        in; KeyError for a reply never asked for."""
        return self._scopes[reply_id]

    async def say(
        self,
        kind: ReplyKind,
        lines: list[Line],
        at: float,
        *,
        turn_id: TurnId | None = None,
        notice: NoticeKind | None = None,
    ) -> Reply:
        """Ask for the reply `lines` say, clause by clause, its scope and its span opened."""
        reply = self.playback.ask(kind, lines, turn_id=turn_id, notice=notice)
        self._opened(reply, tuple(line.caption for line in lines))
        for line in lines:
            if line.speak.audio is not None:
                self._usage.cached(self._tag)
            self._recorder.asked(at, line.speak, line.caption)
            await self._commands.run(line.speak)
        return reply

    async def open_reply(
        self, at: float, *, turn_id: TurnId | None, scope: CancelScope | None = None
    ) -> OpenReply:
        """Open the talker's reply to `turn_id` at `at` (None for an action's outcome, which
        answers no turn), before its first clause: its scope (a new one, or `scope`, which its
        work began in) and its span opened, its clauses added as they come, closed once its
        work is done (open_reply.py)."""
        reply = self.playback.open("answer", turn_id=turn_id)
        opened = self._opened(reply, (), scope=scope)
        return OpenReply(reply_id=reply.reply_id, scope=opened, writer=self, setup=self._setup)

    def _opened(
        self, reply: Reply, captions: tuple[str, ...], *, scope: CancelScope | None = None
    ) -> CancelScope:
        """`reply` is asked for, its clauses' `captions` known so far: its scope (a new one, or
        `scope`), its entry in the heard history and its span opened; its scope."""
        reply_id, turn_id = reply.reply_id, reply.turn_id
        name = f"reply-{reply_id}"
        opened = self._scopes[reply_id] = scope or CancelScope(name=name, clock=self._setup.clock)
        self._history.asked(reply_id, turn_id, captions)
        voice = self._voice
        self._trace.tts_started(
            reply_id, turn_id, model=voice.model, voice=voice.voice, language=self._tag
        )
        return opened

    async def say_line(
        self, line: SpokenLine, *, language: LanguageTag, at: float, turn_id: TurnId | None
    ) -> ReplyId:
        """Say `line`, one of an action's fixed lines (yes_turns.py), in `language` at `at`, as
        a reply of its own answering `turn_id`, written whole at once: its number."""
        reply = await self.open_reply(at, turn_id=turn_id)
        await reply.add_line(line, language=language, at=at)
        await reply.finish(at)
        return reply.reply_id

    async def write(
        self,
        reply_id: ReplyId,
        *,
        text: str,
        caption: str,
        language: LanguageTag,
        at: float,
        audio: AudioChunk | None = None,
        progress: bool = False,
        part: ReadBackPart | None = None,
    ) -> ClauseIndex | None:
        """Ask for the next clause of the open reply `reply_id`: `text` in `language`'s voice
        (or `audio`, a fixed phrase's, with no request), captioned `caption`, the read-back's
        `part` it says, if any; its index, None when it was not asked for (once the reply has
        ended or was closed)."""
        reply = self.playback.reply(reply_id)
        if reply is None or reply.ended_at is not None or not reply.open:
            return None
        speak = Speak(
            reply_id=reply_id,
            clause=len(reply.clauses),
            turn_id=reply.turn_id,
            text=text,
            language=language,
            audio=audio,
        )
        line = Line(speak=speak, caption=caption)
        self.playback.add(reply, line, progress=progress, part=part)
        self._history.added(reply_id, caption)
        if audio is not None:
            self._usage.cached(language)
        self._recorder.asked(at, speak, caption)
        await self._commands.run(speak)
        return speak.clause

    async def show_card(self, reply_id: ReplyId, card: Card) -> bool:
        """Show the caller `card` for the open reply `reply_id`, as `t2v/1`'s `card`; whether it
        was (not once the reply has ended)."""
        reply = self.playback.reply(reply_id)
        if reply is None or reply.ended_at is not None:
            return False
        await self.send(ShowCard(title=card.title, steps=card.steps, source=card.source))
        return True

    async def close(self, reply_id: ReplyId, at: float) -> None:
        """The open reply `reply_id` is written whole at `at`: it ends now when every clause of
        it is done, or with its last."""
        reply = self.playback.reply(reply_id)
        if reply is not None and reply.open and self.playback.close(reply, at):
            await self._end(reply)

    async def greet(self, at: float) -> None:
        """The call connected at `at`: the `hello`, naming the call's language first and the
        agent's others after it, then the greeting, reply 0, from the phrase cache."""
        tags = [self._tag]
        tags += [each.tag for each in self._setup.agent.languages if each.tag != self._tag]
        await self.send(SessionHello(call_id=self._setup.call_id, languages=tuple(tags)))
        greeting = fixed(self._setup, self._setup.language.greeting, reply_id=self.playback.next_id)
        if greeting is not None:
            await self.say("greeting", [greeting], at)

    async def notice(self, kind: NoticeKind, at: float) -> Reply | None:
        """Tell the caller the notice of `kind`: its `notice` message, then spoken from the
        phrase cache as the next reply (none when the cache does not hold it)."""
        text = self._setup.language.notices[kind]
        await self.send(Notice(kind=kind, text=text))
        line = fixed(self._setup, text, reply_id=self.playback.next_id)
        if line is None:
            return None
        audio = line.speak.audio
        if audio is not None:  # a beat first, so it does not run into what was just said
            line = replace(line, speak=replace(line.speak, audio=padded(audio, before_s=BEAT_S)))
        return await self.say("notice", [line], at, notice=kind)

    async def repeat(self, at: float, *, turn_id: TurnId) -> Reply | None:
        """Say again the last reply the caller heard any of (the heard history's), all its
        clauses, as the reply answering `turn_id`: a fixed phrase from the phrase cache, the
        rest through text-to-speech as each was sent; None when no reply was heard."""
        last = self._history.last_reply()
        reply = None if last is None else self.playback.reply(last.reply_id)
        if reply is None:
            return None
        clauses = [(c.caption, c.sent, c.language, c.cached) for c in reply.clauses]
        lines = again(self._setup, clauses, reply_id=self.playback.next_id, turn_id=turn_id)
        return await self.say("repeat", lines, at, turn_id=turn_id) if lines else None

    def heard_audio(self, event: AgentAudio) -> None:
        """The output sent a piece of the agent's audio: counted toward the clause playing."""
        if event.sample_rate > 0:
            self._since_s += len(event.pcm16) / 2 / event.sample_rate

    async def queued(self, event: ClauseQueued) -> Reply | None:
        """A clause's first audio was queued: its caption goes out (a notice shows as its
        `notice` message); the reply it belongs to, while it plays."""
        found = self.playback.queued(event)
        if found is None:
            return None
        reply, clause = found
        if event.held:  # a take the clause cache held: a hit, which sent nothing
            self._usage.cached(clause.language or self._tag)
        now = self.playback.playing()
        if now is not None and now[0] is reply and now[1] == event.clause:
            self._since_s = 0.0  # it plays now: its audio counts from here
        if reply.kind != "notice":
            await self.send(self._caption(reply, event.clause, clause))
        return reply

    async def done(self, event: ClausePlayed | ClauseFailed, *, tell: bool) -> None:
        """A clause played whole or failed; an echo's first failed clause gives the `error`
        notice when `tell`, and the reply ends with its last clause."""
        found = self.playback.done(event)
        if found is None:
            return
        reply, clause = found
        self._since_s = 0.0
        if isinstance(event, ClausePlayed):
            self._usage.played(clause.language or self._tag, event)
            self._history.played(reply.reply_id, event.clause)
            if event.audio_s > 0:
                self._played_s += event.audio_s
                self._played_chars += len(clause.caption)
        else:
            self._events.failed(event.failure, event.retryable, reply.turn_id)
            if reply.kind in ("echo", "repeat", "answer") and not reply.told and tell:
                reply.told = reply.to_tell = True  # at its end, so no clause follows the line
        if reply.ended_at is not None:
            await self._end(reply)

    async def stop(self, at: float, *, client: bool, unducks: int = 0) -> None:
        """Drop every reply asked for so far, naming the newest (`StopSpeaking`), then bring
        the agent's voice back `unducks` times (an overlap's stop: io.py's overlaps); each
        reply ends at once, stopped, the clause playing marked cut in the heard history and,
        under `two_step`, its caption sent again marked cut. The caller's own `stop`
        (`client`) leaves no tail after the replies and emits an `Interrupted` for each; an
        overlap's emits its own (the session's)."""
        dropped = self.playback.in_progress()
        if dropped:
            await self._commands.run(StopSpeaking(reply_id=self.playback.next_id - 1))
        for _ in range(unducks):
            await self.send(Unduck())
        if not dropped:
            return
        self._recorder.line(at, "stopped", replies=[reply.reply_id for reply in dropped])
        playing = self._cut_playing()
        if self._two_step and playing is not None and playing[0].kind != "notice":
            reply, index = playing
            await self.send(self._caption(reply, index, reply.clauses[index], cut=True))
        for reply in self.playback.drop(at, tail=not client):
            reply.stopped = True
            if client:
                self._events.interrupted(reply.turn_id)
            await self._end(reply)
        if self._stopped is not None:
            await self._stopped(at)

    async def cut(self, at: float) -> None:
        """The call ended: every reply still asked for ends, as much of it played as did."""
        self._cut_playing()
        for reply in self.playback.drop(at):
            await self._end(reply)

    def _cut_playing(self) -> tuple[Reply, int] | None:
        """The clause playing as a stop or the call's end cuts it, marked cut in the heard
        history with the share of it played; None when none plays."""
        playing = self.playback.playing()
        if playing is not None:
            reply, index = playing
            fraction = self._since_s / self._length_s(reply.clauses[index])
            self._history.stopped(reply.reply_id, playing=index, fraction=fraction)
        self._since_s = 0.0
        return playing

    def _length_s(self, clause: Clause) -> float:
        """How long `clause`'s audio lasts, estimated by its caption's characters."""
        rate = self._played_s / self._played_chars if self._played_chars else SECONDS_PER_CHARACTER
        return max(rate * len(clause.caption), 1e-3)

    def _caption(self, reply: Reply, index: int, clause: Clause, *, cut: bool = False) -> Caption:
        return Caption(
            speaker="agent",
            text=clause.caption,
            final=True,
            turn_id=reply.turn_id,
            reply_id=reply.reply_id,
            clause=index,
            cut=cut,
        )

    async def _end(self, reply: Reply) -> None:
        if reply.to_tell and reply.ended_at is not None and not (reply.stopped or reply.cut):
            words = (clause.played and not clause.progress for clause in reply.clauses)
            heard = reply.kind == "answer" and any(words)
            await self.notice("cut_off" if heard else "error", reply.ended_at)
        await self._scopes[reply.reply_id].cancel()
        played = self._history.reply(reply.reply_id).played_fraction
        self._events.spoke(reply.turn_id, reply.text, played)
        self._trace.tts_ended(reply.reply_id, reply.numbers(), text=reply.text)
        await self._ended(reply)
