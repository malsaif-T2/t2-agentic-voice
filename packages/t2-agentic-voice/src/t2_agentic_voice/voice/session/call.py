"""One call's session (the design's 12.2): `CallSession`, which the Pipecat side drives through
io.py's `Session` protocol, one event at a time, and which answers with commands. It meets Pipecat
only through io.py, its events (session_events.py) and its commands (commands.py), so a call fed
from text or a file runs the same code as one over WebRTC. io.py says what each side promises.

What it does, and where each part is:

- **The call.** It holds the call in its language (`setup.language` at join, `setup.now` as it
  moves under `stt.live_language = "detected"`: language_moves.py), names it to
  the speech-to-text bridge (`ListenIn`, naming none under `stt.live_language = "auto"`), greets
  the caller once connected (reply 0), and ends the call on the caller's `hangup`, a limit
  (`limits.max_call_s`, `limits.idle_s`), a transport failure, or the runtime's end (call_life.py's
  start, end and finish). A client's `stop` drops every reply in progress at once (io.py's stop
  path).
- **The turns** are turn_book.py's; a turn whose speech began over a reply is not answered under
  `interruptions.mode = "drop"` (io.py's drop rule) and is an overlap under `two_step`, which
  interrupter.py takes, as it takes a command said whole while the agent is silent.
- **The answer.** In echo mode (`session.mode`) each turn is said back in the call's language,
  the cached frame first, then the heard words, clause by clause (echo.py; nothing for a turn
  heard as nothing); with a talker (`setup.talker`) the talker answers (talking.py), its early
  start in Smart Turn's hold and its reply kept behind a newer turn included. An action's
  read-back, the confirming state and its receipt are read_back.py's, the caller's answer to it
  yes_turns.py's, and a confirmed action's job and outcome action_job.py's.
- **Speaking** is speaker.py's (each reply clause by clause, each notice, a stop, a repeat), and
  the replies as they play playback.py's. It tells the caller of a failure and of an end it chose
  with the call language's notices (domain/declaration.py's `NoticeKind`): `error` after a turn
  whose transcript failed, or a reply one of whose clauses failed; `ended` at a limit.
- **Its books** (books.py): the usage of each model, counted from each request's report
  (usage.py); the `CallReport`, written with no text of the call under `storage.var_dir` once
  the call's stream has ended (`aclose`; call_life.py, report.py); each turn's trace and its time
  to first audio (turn_book.py); the recording, kept only when `privacy.record_audio` is on and
  `allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8),
  asked of `setup.consent` itself (recording.py); the heard words, which only voice builds
  (`HeardWords`, invariant 1; heard.py); and what the caller heard (history.py).

Its tests are under tests/t2_agentic_voice/voice/session/, each module's docstring naming its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.voice import protocol as wire
from t2_agentic_voice.voice.session import session_events as on
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.call_life import CallLife
from t2_agentic_voice.voice.session.commands import ListenIn
from t2_agentic_voice.voice.session.echo import echo
from t2_agentic_voice.voice.session.interrupter import Interrupter
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.language_moves import follow
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.report import TurnLog, merged
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
        self._setup, self._commands = setup, commands
        live = setup.settings.stt.live_language
        self._listen = None if live == "auto" else setup.language.primary
        self._lock = asyncio.Lock()
        books = CallBooks.of(setup)
        self._usage, self._recorder, self._events = books.usage, books.recorder, books.events
        self.history = books.history  # what the caller heard
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
                receipt=self._interrupter.receipt,
            )
        self._close = CallLife(
            setup,
            commands,
            books,
            speaker=self._speaker,
            turns=self._turns,
            confirming=self._confirming,
            interrupter=self._interrupter,
            talking=self._talking,
            guarded=self._guarded,
            sync=self._sync_state,
        )
        self._limits = self._close.limits

    async def handle(self, event: on.SessionEvent) -> None:
        """Take one event, as the `Session` protocol says: return soon, never raise."""
        await self._guarded(type(event).__name__, partial(self._take, event))

    async def aclose(self) -> None:
        """Finish the call once its stream has ended, as the `Session` protocol says: the
        report written, never raise."""
        await self._guarded("aclose", self._close.finish)

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
        if self._close.ended is not None:  # only a request's report comes after the end
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
                await self._close.connect(event.at, listen=self._listen)
            case on.TurnOpened():
                self._limits.heard(event.at)
                over = self._turns.opened(event)
                if over is not None:
                    await self._interrupter.opened(event, over)
                elif self._talking is not None:
                    self._talking.opened(self._turns.turn(event.turn_id))
            case on.TurnHeld() | on.HoldResumed():
                held = self._turns.hold(event)
                line = "turn_held" if held else "hold_resumed"
                self._recorder.line(event.at, line, turn_id=event.turn_id)
                if self._talking is not None:
                    await self._talking.hold(event.turn_id, held=held)
            case on.TurnClosed():
                self._limits.heard(event.at)
                self._turns.closed(event)
                if self._talking is not None:
                    await self._talking.release(self._turns.turn(event.turn_id), event.at)
            case on.Transcribing():
                self._turns.transcribing(event)
                self._interrupter.requested(event)
            case on.Transcribed() if event.part == "held":
                heard = self._turns.held(event)
                # a stop or pause request said whole starts nothing (io.py's early start)
                if self._talking is not None and self._interrupter.command(heard) != "stop":
                    await self._talking.held(self._turns.turn(event.turn_id), heard)
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
                    self._confirming.queued(reply, event.clause)
            case on.ClausePlayed() | on.ClauseFailed():
                await self._speaker.done(event, tell=self._close.ending is None)
            case on.FromClient(message=wire.Stop()):
                self._confirming.stopped()
                await self._speaker.stop(event.at, client=True)
                if self._talking is not None:
                    await self._talking.stopped()
            case on.FromClient(message=wire.Hangup()):
                await self._close.end("hangup", event.at, tell=True)
            case on.FromClient(message=wire.ClientStats() as stats):
                self._close.client = merged(self._close.client, stats)
            case on.FromClient(message=wire.Playback(event="started") as played):
                reply = self._playback.reply(played.reply_id)
                self._turns.browser_played(reply, played.clause, event.at)
            case on.TransportFailure():
                self._events.transport(event.stage)
                await self._close.end("transport", event.at, tell=False)
            case on.Ending():
                await self._close.end(event.reason, event.at, tell=event.reason == "server")
        await self._sync_state()

    async def _transcribed(self, event: on.Transcribed) -> None:
        """A turn's own transcript: the call moved first if the turn, not dropped, moved it (an
        overlap's switch request too: language_moves.py); then an overlap's taken by its overlap,
        any other's answered unless, under `two_step`, a command said whole (interrupter.py's
        `alone`), and with a talker a reply kept behind it goes on unless it stopped it."""
        turn, heard = self._turns.transcribed(event)
        if not turn.dropped:
            await follow(self._setup, self._commands, turn, heard, event)
        if turn.overlap:
            await self._interrupter.turn_heard(turn, heard, event)
        else:
            await self._interrupter.alone(turn, heard, event)
            if self._talking is not None:
                await self._talking.taken(turn)

    async def _answer(self, turn: TurnLog, heard: HeardWords | None, event: on.Transcribed) -> None:
        """Say the turn back, unless dropped or the call has ended: its caption, then the
        `error` notice when its request failed, or its echo (nothing for nothing heard); with a
        talker, the talker's reply instead of the echo."""
        ending = self._close.ending
        if self._close.ended is None and not turn.dropped:
            if heard is not None:
                caption = wire.Caption(
                    speaker="caller", text=heard.text, final=True, turn_id=turn.turn_id
                )
                await self._speaker.send(caption)
            if ending is None and event.failure is not None:
                await self._speaker.notice("error", event.at)
            elif ending is None and heard is not None and self._talking is not None:
                await self._talking.answer(turn, heard, event.at)
            elif ending is None and heard is not None:
                lines = echo(self._setup, heard, reply_id=self._playback.next_id)
                if lines:
                    reply = await self._speaker.say("echo", lines, event.at, turn_id=turn.turn_id)
                    turn.reply_id = reply.reply_id
            if ending is None and turn.reply_id is None and turn.fate == "pending":
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
            await self._close.end(self._close.ending or "max_call", reply.ended_at, tell=True)

    def _over(self) -> bool:
        """Whether the call has ended, or is ending at a limit (call_life.py's)."""
        return self._close.over()

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
        """After each step: a yes held over a closing question answered (interrupter.py), an
        action's outcome due said (action_job.py), then the client told what the agent does."""
        if self._close.ended is None and self._close.connected:
            if (code := self._setup.now.untold()) is not None:  # the talker's tool moved the call
                await self._commands.run(ListenIn(language=code))
            if self._talking is not None:  # a yes over a closing question first (D-116)
                await self._interrupter.flush(now := self._setup.clock.now())
                await self._talking.yes.flush(now)
            confirming = await self._close.waits.tell(self._confirming.active)  # read_back_wait.py
            await self._speaker.show_state(awaited=self._turns.awaited, confirming=confirming)
