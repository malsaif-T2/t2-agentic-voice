"""How one call's session (voice/session/call.py) starts, ends and finishes: `CallLife`.

- **The start.** At the call's first `Connected`, its events, trace and recording start, the
  speech-to-text bridge is told the call's language (`ListenIn`), the caller is greeted (reply
  0), and its limits start (limits.py's timers, `limits.max_call_s` and `limits.idle_s`).
- **A limit** plays the `ended` notice, then the call ends once it has played (or at once when
  the cache does not hold it); `idle` holds off while the caller's turn is open.
- **The end**, for whatever reason: its timers stop, every reply still asked for is cut, every
  turn not yet heard is unfinished, then the `ended` message when the caller is told, and the
  `HangUp` last (io.py's end).
- **The finish**, once the call's stream has ended: its timers and its recording finish first,
  then its traces end, its `CallReport` is written with no text of the call (report.py), and
  `CallEnded` goes out.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial

from t2_agentic_voice.core.events import ClientConnection, EndReason
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice import protocol as wire
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.commands import HangUp, ListenIn
from t2_agentic_voice.voice.session.interrupter import Interrupter
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.limits import CallLimits, Limit
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.report import call_report, file_report
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talking import Talking
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)

Guarded = Callable[[str, Callable[[], Awaitable[None]]], Awaitable[None]]


class CallLife:
    """One call's start, end and finish (the module's), its steps run through the session's
    `guarded`, the client told the agent's state after a limit by `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        books: CallBooks,
        *,
        speaker: Speaker,
        turns: TurnBook,
        confirming: Confirming,
        interrupter: Interrupter,
        talking: Talking | None,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
    ) -> None:
        self._setup, self._commands, self._books = setup, commands, books
        self._speaker, self._turns, self._confirming = speaker, turns, confirming
        self._interrupter, self._talking = interrupter, talking
        self._guarded, self._sync = guarded, sync
        self.limits = CallLimits(setup, over=self.over, reached=self._reached)
        self.started_at: datetime = setup.clock.wall()
        self.ended_at: datetime = self.started_at
        self.ended: EndReason | None = None
        self.ending: Limit | None = None  # the limit whose `ended` notice is to play
        self.client: ClientConnection | None = None
        self.connected = self._closed = False

    async def connect(self, at: float, *, listen: str | None) -> None:
        """The call connected at `at`, its speech-to-text to name `listen`: started (the
        module's), once."""
        if self.connected:
            return
        books, self.connected = self._books, True
        self.started_at = books.events.started()
        books.trace.started()
        books.recorder.started(at, self.started_at.isoformat())
        await self._commands.run(ListenIn(language=listen))
        await self._speaker.greet(at)
        self.limits.start(at)
        _log.info("call_started", call_id=self._setup.call_id, language=self._setup.language.tag)

    def over(self) -> bool:
        """Whether the call has ended, or is ending at a limit: no limit is asked for again."""
        return self.ended is not None or self.ending is not None

    async def end(self, reason: EndReason, at: float, *, tell: bool) -> None:
        """End the call for `reason`: the `ended` message when `tell`, then `HangUp`."""
        if self.ended is not None:
            return
        await self.mark_end(reason, at)
        if tell:
            await self._speaker.send(wire.Ended(reason=reason))
        await self._commands.run(HangUp(reason=reason))

    async def mark_end(self, reason: EndReason, at: float) -> None:
        """The call ended: its timers stop, every reply still asked for is cut, and every turn
        not yet heard is unfinished."""
        self.ended, self.ended_at = reason, self._setup.clock.wall()
        self._confirming.end()
        self.limits.stop()
        await self._interrupter.asks.end()
        await self._speaker.cut(at)
        if self._talking is not None:
            await self._talking.end()
        self._turns.end()
        self._books.recorder.line(at, "ended", reason=reason)
        _log.info("call_ended", call_id=self._setup.call_id, reason=reason)

    async def _reached(self, limit: Limit) -> None:
        await self._guarded(limit, partial(self._limit, limit))

    async def _limit(self, limit: Limit) -> None:
        """At `limit`: the `ended` notice, then the call ends once it has played (or at once
        when the cache does not hold it). `idle` holds off while the caller's turn is open."""
        now = self._setup.clock.now()
        if self.over() or not self.limits.passed(limit, now):
            return
        if limit == "idle" and not self._turns.all_closed:
            self.limits.heard(now)
            return
        self.ending = limit
        if await self._speaker.notice("ended", now) is None:
            await self.end(limit, now, tell=True)
        await self._sync()

    async def finish(self) -> None:
        """The call's stream ended: its timers and its recording finish first, whatever comes
        after, then its traces end, its report is written, and `CallEnded` goes out."""
        if self._closed:
            return
        self._closed = True
        books = self._books
        await self.limits.aclose()
        await books.recorder.aclose()
        if self.ended is None:  # a stream that ended with no end: as the runtime stopping
            await self.mark_end("server", self._setup.clock.now())
        turns = self._turns.close()  # each trace not yet ended ends with how it ended
        report = call_report(
            self._setup,
            started_at=self.started_at,
            ended_at=self.ended_at,
            ended_by=self.ended or "server",
            turns=turns,
            usage=books.usage.report(),
            client=self.client,
        )
        await file_report(report, self._setup, trace=books.trace, events=books.events)
