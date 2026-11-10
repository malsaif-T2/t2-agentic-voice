"""One call's session (the design's 12.2), built by plan 003's Track D.

In echo mode (`session.mode`, Q3) it holds the whole call in its language (`setup.language`,
fixed at join), names it to the speech-to-text bridge (`ListenIn`), greets the caller once
connected (reply 0), then says each turn back in that language's voice, one voice per reply:
the cached frame first, once the turn's transcript is in, then the heard words, clause by
clause, while the text-to-speech request runs; an empty transcript is said back as nothing and
kept on the timeline. Each reply is the next from 0, its clauses keyed on it (io.py's replies).
A turn whose speech began while any reply played, the greeting included, or within 300 ms after
a reply's last clause played (none after the caller's own `stop`), is not said back under
`interruptions.mode = "drop"` (io.py's drop rule; plan 003's decision log), so the agent never
echoes its own voice; under `two_step` it is an overlap, which interrupter.py takes (io.py's
overlaps), as it takes a stop, pause or repeat request said whole while the agent is silent,
never said back. A client's `stop` drops at once every clause asked for so far, whatever its reply
(`StopSpeaking` naming the newest reply: io.py's stop path), each reply it drops counted as done
and its cancel scope cancelled, and the session listens again; `hangup` ends the call. It tells the
caller of a failure, and of an end it chose, with the call language's notices
(`setup.language.notices`; domain/declaration.py's `NoticeKind`): `error` after a turn it would
say back whose transcript failed, or an echo one of whose clauses failed; `ended` when it ends
the call at a limit, `limits.max_call_s` or `limits.idle_s` (plan 003, Q4), hanging up once the
notice has played or failed, or at once when a stop drops it. Each goes out as a `notice`
message, whose text the client shows, and is spoken from the phrase cache as the next reply,
naming no turn; `busy` is admission control's, at join. Whatever ends the call, its `HangUp`
leaves a turn still open, or with its transcript still to come, unfinished (io.py's end).

It says the heard words as echo.py says them, a fixed phrase from the phrase cache; a
transcript the filter for text from silence takes for no words (turn_book.py; on by default
since the registered rule F, D-063) is said back as nothing.

It counts each model's usage from each request's report (io.py's usage), a request the call's
end cancelled included, keeps the call's `CallReport` and writes its numbers, with no text of
the call, to a file under `storage.var_dir`, once the call's stream has ended (`aclose`);
traces each turn; records the call only when `privacy.record_audio` is on and
`allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8),
asked by the recorder of `setup.consent` itself, never of a copy or of a consent rebuilt or
built here (recording.py); builds `HeardWords`, which only `voice` may build (invariant 1); and
keeps what the caller heard (history.py), all in its books (books.py). It meets Pipecat only
through io.py and its events and commands. Its turns are turn_book.py's, its limit timers
limits.py's, how it speaks speaker.py's, and its overlaps interrupter.py's. Its tests are under
tests/t2_agentic_voice/voice/session/, each module's docstring saying which it holds.

With a talker (`setup.talker`, plan 006) it answers each turn with the talker instead of the
echo (talking.py): the turn's caption, then the talker's reply, spoken clause by clause as it is
written; the interruptions are handed to it (interrupter.py); and a turn said while the agent
was silent starts it early, at Smart Turn's "complete", playing nothing before the hold ends
(io.py's early start), nor after a client's `stop` in the hold or once the call ends or is
ending; and while a newer turn, no overlap of the talker's reply, is open, nothing more of that
reply plays until the turn is taken: its words stop the reply, and a turn heard as nothing lets
it go on (talking.py's kept reply). Every turn's time to first audio is timed to the reply's
first audible frame sent, and to the browser's playback of it (turn_book.py). An action's
read-back, the call's confirming state and its receipt are read_back.py's (plan 007).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial

from t2_agentic_voice.core.events import ClientConnection, EndReason
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.voice import protocol as wire
from t2_agentic_voice.voice.session import session_events as on
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.commands import HangUp, ListenIn
from t2_agentic_voice.voice.session.echo import echo
from t2_agentic_voice.voice.session.interrupter import Interrupter
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.limits import CallLimits, Limit
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.report import (
    TurnLog,
    call_report,
    file_report,
    merged,
)
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talking import Talking
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)


class CallSession:
    """One call's session: a `Session`, driven by the Pipecat side's events, answering with
    `commands`. Built when the call's offer is answered, cheaply and with no IO; it begins at
    the call's `Connected`, gives its last command with its `HangUp`, and finishes at
    `aclose`."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        settings, language = setup.settings, setup.language
        self._setup, self._commands, self._language = setup, commands, language
        self._listen = language.primary if settings.stt.live_language == "session" else None
        self._lock = asyncio.Lock()
        books = CallBooks.of(setup)
        self._usage, self._recorder, self._events = books.usage, books.recorder, books.events
        self._trace, self.history = books.trace, books.history  # what the caller heard
        self._speaker = Speaker(
            setup, commands, books, ended=self._reply_ended, stopped=self._replies_stopped
        )
        self._playback = self._speaker.playback
        self._turns = TurnBook(setup, books, listen=self._listen, playback=self._playback)
        self._confirming = Confirming(setup, self._playback)  # an action's read-back
        self._interrupter = Interrupter(
            setup,
            commands,
            books,
            speaker=self._speaker,
            turns=self._turns,
            over=self._over,
            answer=self._answer,
            guarded=self._guarded,
            sync=self._sync_state,
            confirming=self._confirming,
        )
        self._talking: Talking | None = None
        if setup.talker is not None:
            self._talking = Talking(
                setup,
                books,
                talker=setup.talker,
                speaker=self._speaker,
                turns=self._turns,
                guarded=self._guarded,
                sync=self._sync_state,
                over=self._over,
                confirming=self._confirming,
            )
        self._limits = CallLimits(setup, over=self._over, reached=self._reached)
        self._started_at = self._ended_at = setup.clock.wall()
        self._connected = self._closed = False
        self._ended: EndReason | None = None
        self._ending: Limit | None = None  # the limit whose `ended` notice is to play
        self._client: ClientConnection | None = None

    async def handle(self, event: on.SessionEvent) -> None:
        """Take one event, as the `Session` protocol says: return soon, never raise."""
        await self._guarded(type(event).__name__, partial(self._take, event))

    async def aclose(self) -> None:
        """Finish the call once its stream has ended, as the `Session` protocol says: the
        report written, never raise."""
        await self._guarded("aclose", self._finish)

    async def _guarded(self, step: str, run: Callable[[], Awaitable[None]]) -> None:
        """Run one step of the session's, one at a time; a failure is logged by its kind alone,
        and the call goes on."""
        try:
            async with self._lock:
                await run()
        except Exception as error:
            failure = type(error).__qualname__
            _log.error("session_step_failed", call_id=self._id, step=step, failure=failure)

    async def _take(self, event: on.SessionEvent) -> None:
        if self._ended is not None:  # only a request's report comes after the end
            if isinstance(event, on.Transcribing):
                self._usage.transcribing(event)
            elif isinstance(event, on.Synthesizing):
                self._speaker.synthesizing(event)
            return
        self._recorder.take(event)
        match event:
            case on.AgentAudio():
                self._speaker.heard_audio(event)
                self._turns.heard_audio(self._playback.playing(), event)
                return
            case on.CallerAudio():
                return
            case on.Connected():
                await self._connected_at(event.at)
            case on.TurnOpened():
                self._limits.heard(event.at)
                over = self._turns.opened(event)
                if over is not None:
                    await self._interrupter.opened(event, over)
                elif self._talking is not None:
                    self._talking.opened(self._turns.turn(event.turn_id))
            case on.TurnHeld() | on.HoldResumed():
                await self._hold(event)
            case on.TurnClosed():
                self._limits.heard(event.at)
                self._turns.closed(event)
                if self._talking is not None:
                    await self._talking.release(self._turns.turn(event.turn_id), event.at)
            case on.Transcribing():
                self._turns.transcribing(event)
                self._interrupter.requested(event)
            case on.Transcribed() if event.part == "held":
                await self._held(event)
            case on.Transcribed() if event.part != "turn":
                await self._interrupter.heard(event)
            case on.Transcribed():
                await self._transcribed(event)
            case on.Synthesizing():
                self._speaker.synthesizing(event)
            case on.ClauseQueued():
                reply = await self._speaker.queued(event)
                if reply is not None:
                    self._turns.first_audio(reply, event.clause, event.at)
            case on.ClausePlayed() | on.ClauseFailed():
                await self._speaker.done(event, tell=self._ending is None)
            case on.FromClient(message=wire.Stop()):
                self._confirming.stopped()
                await self._speaker.stop(event.at, client=True)
                if self._talking is not None:
                    await self._talking.stopped()
            case on.FromClient(message=wire.Hangup()):
                await self._end("hangup", event.at, tell=True)
            case on.FromClient(message=wire.ClientStats() as stats):
                self._client = merged(self._client, stats)
            case on.FromClient(message=wire.Playback(event="started") as played):
                reply = self._playback.reply(played.reply_id)
                self._turns.browser_played(reply, played.clause, event.at)
            case on.TransportFailure():
                self._events.transport(event.stage)
                await self._end("transport", event.at, tell=False)
            case on.Ending():
                await self._end(event.reason, event.at, tell=event.reason == "server")
        await self._sync_state()

    async def _connected_at(self, at: float) -> None:
        if self._connected:
            return
        self._connected, self._started_at = True, self._events.started()
        self._trace.started()
        self._recorder.started(at, self._started_at.isoformat())
        await self._commands.run(ListenIn(language=self._listen))
        await self._speaker.greet(at)
        self._limits.start(at)
        _log.info("call_started", call_id=self._id, language=self._language.tag)

    async def _transcribed(self, event: on.Transcribed) -> None:
        """A turn's own transcript: an overlap's taken by its overlap, any other's answered
        unless, under `two_step`, it is a command said whole (interrupter.py's `alone`); then,
        with a talker, a reply kept behind it goes on unless it stopped it (talking.py)."""
        turn, heard = self._turns.transcribed(event)
        if turn.overlap:
            await self._interrupter.turn_heard(turn, heard, event)
        else:
            await self._interrupter.alone(turn, heard, event)
            if self._talking is not None:
                await self._talking.taken(turn)

    async def _hold(self, event: on.TurnHeld | on.HoldResumed) -> None:
        """The turn's hold began, or the caller resumed within it (io.py's early start)."""
        held = isinstance(event, on.TurnHeld)
        self._recorder.line(
            event.at, "turn_held" if held else "hold_resumed", turn_id=event.turn_id
        )
        if self._talking is None:
            return
        if held:
            self._talking.hold_began(event.turn_id)
        else:
            await self._talking.resumed(event.turn_id)

    async def _held(self, event: on.Transcribed) -> None:
        """A turn's `held` transcript, its speech so far when its hold began: with a talker,
        the talker starts on it for a turn said while the agent was silent, unless it is a stop
        or pause request said whole (io.py's early start)."""
        heard = self._turns.held(event)
        turn = self._turns.turn(event.turn_id)
        if self._talking is None or heard is None or self._over():
            return
        if turn.overlap or turn.dropped or turn.closed:
            return
        if self._interrupter.command(heard) != "stop":
            await self._talking.held(turn, heard)

    async def _answer(self, turn: TurnLog, heard: HeardWords | None, event: on.Transcribed) -> None:
        """Say the turn back, unless dropped or the call has ended: its caption, then the
        `error` notice when its request failed, or its echo (nothing for nothing heard); with a
        talker, the talker's reply instead of the echo."""
        if self._ended is None and not turn.dropped:
            if heard is not None:
                caption = wire.Caption(
                    speaker="caller", text=heard.text, final=True, turn_id=turn.turn_id
                )
                await self._speaker.send(caption)
            if self._ending is None and event.failure is not None:
                await self._speaker.notice("error", event.at)
            elif self._ending is None and heard is not None and self._talking is not None:
                await self._talking.answer(turn, heard, event.at)
            elif self._ending is None and heard is not None:
                lines = echo(self._setup, heard, reply_id=self._playback.next_id)
                if lines:
                    reply = await self._speaker.say("echo", lines, event.at, turn_id=turn.turn_id)
                    turn.reply_id = reply.reply_id
            if self._ending is None and turn.reply_id is None and turn.fate == "pending":
                self._turns.ended(turn, "answered")
        self._turns.settle(turn)

    async def _replies_stopped(self, at: float) -> None:
        """A stop dropped the replies in progress (the speaker's word, whoever asked): a chat
        model's request on an uncertain overlap is cancelled (overlap_ask.py)."""
        await self._interrupter.asks.stopped(at)

    async def _reply_ended(self, reply: Reply) -> None:
        """A reply ended, however (the speaker's word): its turn settles, and an `ended` notice
        ends the call."""
        self._turns.reply_ended(reply)
        self._confirming.reply_ended(reply)
        if reply.notice == "ended" and reply.ended_at is not None:
            await self._end(self._ending or "max_call", reply.ended_at, tell=True)

    async def _end(self, reason: EndReason, at: float, *, tell: bool) -> None:
        """End the call for `reason`: the `ended` message when `tell`, then `HangUp`."""
        if self._ended is not None:
            return
        await self._mark_end(reason, at)
        if tell:
            await self._speaker.send(wire.Ended(reason=reason))
        await self._commands.run(HangUp(reason=reason))

    async def _mark_end(self, reason: EndReason, at: float) -> None:
        """The call ended: its timers stop, every reply still asked for is cut, and every turn
        not yet heard is unfinished."""
        self._ended, self._ended_at = reason, self._setup.clock.wall()
        self._confirming.end()
        self._limits.stop()
        await self._interrupter.asks.end()
        await self._speaker.cut(at)
        if self._talking is not None:
            await self._talking.end()
        self._turns.end()
        self._recorder.line(at, "ended", reason=reason)
        _log.info("call_ended", call_id=self._id, reason=reason)

    def _over(self) -> bool:
        """Whether the call has ended, or is ending at a limit: no limit is asked for again."""
        return self._ended is not None or self._ending is not None

    async def _reached(self, limit: Limit) -> None:
        await self._guarded(limit, partial(self._limit, limit))

    async def _limit(self, limit: Limit) -> None:
        """At `limit`: the `ended` notice, then the call ends once it has played (or at once
        when the cache does not hold it). `idle` holds off while the caller's turn is open."""
        now = self._setup.clock.now()
        if self._over() or not self._limits.passed(limit, now):
            return
        if limit == "idle" and not self._turns.all_closed:
            self._limits.heard(now)
            return
        self._ending = limit
        if await self._speaker.notice("ended", now) is None:
            await self._end(limit, now, tell=True)
        await self._sync_state()

    async def _finish(self) -> None:
        """The call's stream ended: its timers and its recording finish first, whatever comes
        after, then its traces end, its report is written, and `CallEnded` goes out."""
        if self._closed:
            return
        self._closed = True
        await self._limits.aclose()
        await self._recorder.aclose()
        if self._ended is None:  # a stream that ended with no end: as the runtime stopping
            await self._mark_end("server", self._setup.clock.now())
        turns = self._turns.close()  # each trace not yet ended ends with how it ended
        report = call_report(
            self._setup,
            started_at=self._started_at,
            ended_at=self._ended_at,
            ended_by=self._ended or "server",
            turns=turns,
            usage=self._usage.report(),
            client=self._client,
        )
        await file_report(report, self._setup, trace=self._trace, events=self._events)

    @property
    def setup(self) -> CallSetup:
        """What the call started with."""
        return self._setup

    @property
    def playback(self) -> Playback:
        """The agent's replies as they play (playback.py), read-only for a test's reads."""
        return self._playback

    @property
    def _id(self) -> str:
        return self._setup.call_id

    async def _sync_state(self) -> None:
        """Tell the client what the agent is doing, when it changed."""
        if self._ended is None and self._connected:
            confirming = self._confirming.active
            await self._speaker.show_state(awaited=self._turns.awaited, confirming=confirming)
