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

It says the heard words as the agent's pronunciation map says them: it applies `pronounce`
(domain/text/pronounce.py) with `agent.pronounce`, in the call's language, to a reply's text
before it cuts it with `split_clauses` at `setup.max_chars`, so each clause is measured on the
said form; it gives each clause's `Speak` the text the provider is sent, `provider_text` of the
clause (domain/text/invisible.py), which is never longer; and the agent's caption shows the
said form, clause by clause. A fixed phrase is played from the phrase cache, which applied
the map itself, and captioned as written.

It counts each model's usage from each request's report (io.py's usage), a request the call's
end cancelled included, keeps the call's `CallReport` and writes its numbers, with no text of
the call, to a file under `storage.var_dir`, once the call's stream has ended (`aclose`);
traces each turn; records the call only when `privacy.record_audio` is on and
`allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8);
and builds `HeardWords`, which only `voice` may build (invariant 1). It meets Pipecat only
through io.py and its events and commands. The recorder asks `allows_recording` of
`setup.consent` itself, the very object the identity source returned, never the consent's
class, and never copies or rebuilds a consent: only the instance the seal validated, unchanged
since, allows recording, so a copy of it (even with no change, and by any path: `copy.copy`, a
pickle, `Consent.model_copy`), a consent rebuilt, re-typed or rewritten in place, or one built
here keeps nothing; and only adapters/join_tokens.py gives the seal (`[[restricted]]`).

Its tests, the plan's list and those this contract named beyond it, are under
tests/t2_agentic_voice/voice/session/, each module's docstring saying which it holds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Literal

from t2_agentic_voice.core.events import ClientConnection, EndReason
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing_tts import CallTrace, resource_attributes
from t2_agentic_voice.voice import protocol as wire
from t2_agentic_voice.voice.session import session_events as on
from t2_agentic_voice.voice.session.commands import HangUp, ListenIn
from t2_agentic_voice.voice.session.echo import echo, fixed
from t2_agentic_voice.voice.session.heard import heard_words
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.playback import Reply, Speaker
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import (
    CallEvents,
    TurnLog,
    call_report,
    merged,
    span_attributes,
    write_report,
)
from t2_agentic_voice.voice.session.usage import Usage

_log = get_logger(__name__)
# The session's own timers: the call's length, and the time with nothing heard (plan 003, Q4).
Limit = Literal["max_call", "idle"]


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
        self._turns: dict[int, TurnLog] = {}
        self._started_at = self._ended_at = setup.clock.wall()
        self._connected = self._closed = False
        self._ended: EndReason | None = None
        self._ending: Limit | None = None  # the limit whose `ended` notice is to play
        self._deadlines: dict[Limit, float] = {}
        self._timers: list[asyncio.Task[None]] = []
        self._state: wire.CallState | None = None
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
                self._synthesizing(event)
            return
        self._recorder.take(event)
        idle = self._setup.settings.limits.idle_s
        match event:
            case on.CallerAudio() | on.AgentAudio():
                return
            case on.Connected():
                await self._connected_at(event.at)
            case on.TurnOpened():
                turn = self._turn(event.turn_id)
                turn.speech_at, self._deadlines["idle"] = event.speech_at, event.at + idle
                turn.dropped = self._playback.heard_over(event.speech_at)
                self._trace.turn_opened(event.turn_id)
            case on.TurnClosed():
                turn = self._turn(event.turn_id)
                turn.closed, turn.speech_ended_at = True, event.speech_ended_at
                self._deadlines["idle"] = event.at + idle
                self._settle(turn)
            case on.Transcribing():
                self._usage.transcribing(event)
                self._turn(event.turn_id).requested = True
                model, seconds = self._setup.settings.stt.model, event.audio_s
                self._trace.stt_sent(
                    event.turn_id, model=model, language=self._listen, audio_seconds=seconds
                )
            case on.Transcribed():
                await self._transcribed(event)
            case on.Synthesizing():
                self._synthesizing(event)
            case on.ClauseQueued():
                reply = await self._speaker.queued(event)
                if reply is not None and reply.turn_id is not None:
                    turn = self._turn(reply.turn_id)
                    turn.first_audio_at = turn.first_audio_at or event.at
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
        limits = self._setup.settings.limits
        self._deadlines = {"max_call": at + limits.max_call_s, "idle": at + limits.idle_s}
        self._timers = [asyncio.create_task(self._timer(limit)) for limit in self._deadlines]
        _log.info("call_started", call_id=self._id, language=self._language.tag)

    async def _transcribed(self, event: on.Transcribed) -> None:
        turn, transcript = self._turn(event.turn_id), event.transcript
        turn.transcribed_at = event.at
        self._usage.transcribed(event)
        self._trace.stt_heard(
            event.turn_id,
            text="" if transcript is None else transcript.text,
            language=None if transcript is None else transcript.language,
            billed_seconds=None if transcript is None else transcript.billed_seconds,
        )
        heard = heard_words(event)
        turn.heard = "" if heard is None else heard.text
        self._recorder.heard(event.at, event.turn_id, turn.heard, dropped=turn.dropped)
        if event.failure is not None:
            self._events.failed(event.failure, event.retryable, event.turn_id)
        if not turn.dropped:
            self._events.heard(turn.turn_id, turn.heard)
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
        self._settle(turn)

    def _synthesizing(self, event: on.Synthesizing) -> None:
        clause = self._playback.requested(event)
        if clause is not None:
            self._usage.synthesizing(self._language.tag, clause.characters)

    async def _reply_ended(self, reply: Reply) -> None:
        """A reply ended, however (the speaker's word): its turn settles, and an `ended` notice
        ends the call."""
        if reply.turn_id is not None:
            turn = self._turn(reply.turn_id)
            turn.stopped = turn.stopped or reply.stopped
            turn.tts_first_audio_s = reply.first_audio_s
            self._settle(turn)
        if reply.notice == "ended" and reply.ended_at is not None:
            await self._end(self._ending or "max_call", reply.ended_at, tell=True)

    def _settle(self, turn: TurnLog) -> None:
        """Once a turn has closed, been heard and had its reply played, its trace ends and its
        times go out (none for a dropped turn)."""
        reply = None if turn.reply_id is None else self._playback.reply(turn.reply_id)
        if turn.done or not (turn.closed and turn.transcribed):
            return
        if reply is not None and reply.ended_at is None:
            return
        turn.done = True
        self._trace.turn_ended(turn.turn_id, turn.outcome())
        if not turn.dropped:
            self._events.metrics(turn)

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
        for task in self._timers:
            if task is not asyncio.current_task():
                task.cancel()
        await self._speaker.cut(at)
        for turn in self._turns.values():
            turn.unfinished = not turn.transcribed
        self._recorder.line(at, "ended", reason=reason)
        _log.info("call_ended", call_id=self._id, reason=reason)

    async def _timer(self, limit: Limit) -> None:
        """Sleep until `limit`'s deadline, which hearing the caller moves for `idle`; then tell
        the caller, once."""
        clock = self._setup.clock
        while self._ended is None and self._ending is None:
            wait = self._deadlines[limit] - clock.now()
            if wait > 0:
                await clock.sleep(wait)
                continue
            await self._guarded(limit, partial(self._limit, limit))
            if self._deadlines[limit] <= clock.now():
                return

    async def _limit(self, limit: Limit) -> None:
        """At `limit`: the `ended` notice, then the call ends once it has played (or at once
        when the cache does not hold it). `idle` holds off while the caller's turn is open."""
        now = self._setup.clock.now()
        if self._ended is not None or self._ending is not None or now < self._deadlines[limit]:
            return
        if limit == "idle" and not all(turn.closed for turn in self._turns.values()):
            self._deadlines[limit] = now + self._setup.settings.limits.idle_s
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
        for task in self._timers:
            task.cancel()
        await asyncio.gather(*self._timers, return_exceptions=True)
        await self._recorder.aclose()
        if self._ended is None:  # a stream that ended with no end: as the runtime stopping
            await self._mark_end("server", self._setup.clock.now())
        for turn in self._turns.values():
            if not turn.done:  # its trace ends with how it ended
                self._trace.turn_ended(turn.turn_id, turn.outcome())
        report = call_report(
            self._setup,
            started_at=self._started_at,
            ended_at=self._ended_at,
            ended_by=self._ended or "server",
            turns=list(self._turns.values()),
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

    def _turn(self, turn_id: int) -> TurnLog:
        return self._turns.setdefault(turn_id, TurnLog(turn_id=turn_id))

    async def _sync_state(self) -> None:
        """Tell the client what the agent is doing, when it changed."""
        if self._ended is not None or not self._connected:
            return
        state: wire.CallState = "listening"
        if self._playback.speaking:
            state = "speaking"
        elif self._playback.waiting or any(turn.awaited for turn in self._turns.values()):
            state = "thinking"
        if state != self._state:
            self._state = state
            await self._speaker.send(wire.State(state=state))
