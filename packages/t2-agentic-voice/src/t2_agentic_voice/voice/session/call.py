"""One call's session (the design's 12.2), built by plan 003's Track D.

In echo mode (`session.mode`, Q3) it holds the whole call in its language (`setup.language`,
fixed at join), names it to the speech-to-text bridge (`ListenIn`), greets the caller once
connected (reply 0), then says each turn back in that language's voice, one voice per reply:
the cached frame first, once the turn's transcript is in, then the heard words, clause by
clause, while the text-to-speech request runs; an empty transcript is said back as nothing and
kept on the timeline. Each reply is the next from 0, its clauses keyed on it (io.py's replies).
A turn whose speech began while any reply played, the greeting included, or within 300 ms after
a reply's last clause played, is not said back (io.py's drop rule; plan 003's decision log), so
the agent never echoes its own voice. A client's `stop` drops at once every clause asked for so
far, whatever its reply (`StopSpeaking` naming the newest reply: io.py's stop path), each reply
it drops counted as done, and the session listens again; `hangup` ends the call. It tells the
caller of a failure, and of an end it chose, with the call language's notices
(`setup.language.notices`; domain/declaration.py's `NoticeKind`): `error` after a turn it would
say back whose transcript failed, or an echo one of whose clauses failed; `ended` when it ends
the call at a limit, `limits.max_call_s` or `limits.idle_s` (plan 003, Q4), hanging up once the
notice has played or failed, or at once when a stop drops it. Each goes out as a `notice`
message, whose text the client shows, and is spoken from the phrase cache as the next reply,
naming no turn; `busy` is admission control's, at join. Whatever ends the call, its `HangUp`
leaves a turn still open, or with its transcript still to come, unfinished (io.py's end).

It says the heard words as echo.py says them: the agent's pronunciation map applied, cut into
clauses on the said form and packed into requests of at most `setup.max_chars`, at most
`MAX_ECHO_REQUESTS` an echo, each sent as the provider's text and captioned as said; a fixed
phrase is played from the phrase cache and captioned as written.

It counts each model's usage from each request's report (io.py's usage), a request the call's
end cancelled included, keeps the call's `CallReport` and writes its numbers, with no text of
the call, to a file under `storage.var_dir`, once the call's stream has ended (`aclose`);
traces each turn; records the call only when `privacy.record_audio` is on and
`allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8),
asked by the recorder of `setup.consent` itself, never of a copy or of a consent rebuilt or
built here (recording.py); and builds `HeardWords`, which only `voice` may build (invariant 1).
It meets Pipecat only through io.py and its events and commands. Its turns are turn_book.py's,
its limit timers limits.py's, and how it speaks speaker.py's.

Its tests, the plan's list and those this contract named beyond it, are under
tests/t2_agentic_voice/voice/session/, each module's docstring saying which it holds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial

from t2_agentic_voice.core.events import ClientConnection, EndReason
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing_tts import CallTrace, resource_attributes
from t2_agentic_voice.voice import protocol as wire
from t2_agentic_voice.voice.session import session_events as on
from t2_agentic_voice.voice.session.commands import HangUp, ListenIn
from t2_agentic_voice.voice.session.echo import echo, fixed
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.limits import CallLimits, Limit
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import (
    CallEvents,
    call_report,
    merged,
    span_attributes,
    write_report,
)
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.usage import Usage

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
        self._usage = Usage(settings, language.tag)
        self._recorder = CallRecorder(setup)
        self._events = CallEvents(setup)
        models = (settings.stt.model, self._usage.model(language.tag))
        resource = resource_attributes(
            settings, agent=setup.agent.name, models=models, consent_version=setup.consent.version
        )
        self._trace = CallTrace(setup.tracing, call_id=setup.call_id, resource=resource)
        self._speaker = Speaker(
            setup,
            commands,
            usage=self._usage,
            trace=self._trace,
            recorder=self._recorder,
            events=self._events,
            ended=self._reply_ended,
        )
        self._playback = self._speaker.playback
        self._turns = TurnBook(
            setup,
            listen=self._listen,
            usage=self._usage,
            trace=self._trace,
            recorder=self._recorder,
            events=self._events,
            playback=self._playback,
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
            case on.CallerAudio() | on.AgentAudio():
                return
            case on.Connected():
                await self._connected_at(event.at)
            case on.TurnOpened():
                self._limits.heard(event.at)
                self._turns.opened(event)
            case on.TurnClosed():
                self._limits.heard(event.at)
                self._turns.closed(event)
            case on.Transcribing():
                self._turns.transcribing(event)
            case on.Transcribed():
                await self._transcribed(event)
            case on.Synthesizing():
                self._speaker.synthesizing(event)
            case on.ClauseQueued():
                reply = await self._speaker.queued(event)
                if reply is not None:
                    self._turns.first_audio(reply, event.at)
            case on.ClausePlayed() | on.ClauseFailed():
                await self._speaker.done(event, tell=self._ending is None)
            case on.FromClient(message=wire.Stop()):
                await self._speaker.stop(event.at)
            case on.FromClient(message=wire.Hangup()):
                await self._end("hangup", event.at, tell=True)
            case on.FromClient(message=wire.ClientStats() as stats):
                self._client = merged(self._client, stats)
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
        tags = [self._language.tag]
        tags += [each.tag for each in self._setup.agent.languages if each.tag != tags[0]]
        await self._speaker.send(wire.SessionHello(call_id=self._id, languages=tuple(tags)))
        greeting = fixed(self._setup, self._language.greeting, reply_id=self._playback.next_id)
        if greeting is not None:
            await self._speaker.say("greeting", [greeting], at)
        self._limits.start(at)
        _log.info("call_started", call_id=self._id, language=self._language.tag)

    async def _transcribed(self, event: on.Transcribed) -> None:
        turn, heard = self._turns.transcribed(event)
        if not turn.dropped:
            if heard is not None:
                caption = wire.Caption(
                    speaker="caller", text=heard.text, final=True, turn_id=turn.turn_id
                )
                await self._speaker.send(caption)
            if self._ending is None and event.failure is not None:
                await self._speaker.notice("error", event.at)
            elif self._ending is None and heard is not None:
                lines = echo(self._setup, heard, reply_id=self._playback.next_id)
                if lines:
                    reply = await self._speaker.say("echo", lines, event.at, turn_id=turn.turn_id)
                    turn.reply_id, turn.said = reply.reply_id, reply.text
        self._turns.settle(turn)

    async def _reply_ended(self, reply: Reply) -> None:
        """A reply ended, however (the speaker's word): its turn settles, and an `ended` notice
        ends the call."""
        self._turns.reply_ended(reply)
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
        self._limits.stop()
        await self._speaker.cut(at)
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
        self._trace.close(span_attributes(report))
        try:
            await asyncio.to_thread(write_report, report, self._setup.settings.storage.var_dir)
        except OSError as error:
            _log.warning("report_not_written", call_id=self._id, failure=type(error).__qualname__)
        self._events.ended(report)

    @property
    def _id(self) -> str:
        return self._setup.call_id

    async def _sync_state(self) -> None:
        """Tell the client what the agent is doing, when it changed."""
        if self._ended is None and self._connected:
            await self._speaker.show_state(awaited=self._turns.awaited)
