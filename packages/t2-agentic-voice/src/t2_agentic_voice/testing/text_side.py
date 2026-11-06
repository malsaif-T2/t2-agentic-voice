"""The side of a `TextCall` that a real call's Pipecat modules play (voice/session/io.py; plan 006):
what the session's commands do and the events it is handed, with no audio and no Pipecat, so
the session under test is the real one (testing/text_call.py).

- **`VirtualClock`**: a call's `Clock` that moves only when moved (`advance`, or `run_to`, the
  next sleep due), each sleep that ends by then woken at its own end, in order, what it woke run
  before the next.
- **`TextPhrases`**: the phrase audio of the agent's fixed phrases and its tools' progress lines,
  each declared at the start as the phrase cache declares them, silence of no length (a text call
  plays no audio); LookupError for any other text, as the cache refuses one.
- **`TextSide`**: where the session's commands go (`Commands`), and the stream of events it is
  handed, one at a time and in order, by a task of its own, so no command waits on the session
  (TD-068). A `Speak` is the fake text-to-speech's: its request reported as it goes (none for a
  fixed phrase), its first audio queued at once, and its clause played `chars_per_second` later,
  clauses one after another; `StopSpeaking` drops every clause asked for so far, and every event
  of one still waiting (io.py's stop path); `HearOverlap` marks a turn an overlap, whose whole
  overlap part the call's caller then sends (the fake speech-to-text); each `Send` is kept;
  `HangUp` ends the call, after which only a request's report is handed.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from t2_agentic_voice.core.events import EndReason
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import SessionMessage
from t2_agentic_voice.voice.session.commands import (
    Command,
    HangUp,
    HearOverlap,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.io import Clock, Session
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    SessionEvent,
    Synthesizing,
    Transcribing,
)

# When a virtual clock's time of day starts: a fixed instant, so a text call is deterministic.
VIRTUAL_START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
# The output rate a text call's silence is given at.
_RATE = 24_000
# A clause's events, keyed on its reply and index, which a stop drops (io.py's stop path).
_CLAUSE_EVENTS = (Synthesizing, ClauseQueued, ClausePlayed, ClauseFailed)
_REPORTS = (Transcribing, Synthesizing)


async def settle(turns: int = 60) -> None:
    """Let what was woken run, a few turns of the event loop."""
    for _ in range(turns):
        await asyncio.sleep(0)


class VirtualClock:
    """A call's clock that moves only when moved (the module's docstring): `now` starts at 0 and
    `wall` at VIRTUAL_START plus the same seconds."""

    def __init__(self) -> None:
        self._now = 0.0
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    def now(self) -> float:
        return self._now

    def wall(self) -> datetime:
        return VIRTUAL_START + timedelta(seconds=self._now)

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        woken = asyncio.get_running_loop().create_future()
        heapq.heappush(self._sleepers, (self._now + seconds, next(self._order), woken))
        await woken

    @property
    def next_due(self) -> float | None:
        """When the next sleep not cancelled ends; None when none waits."""
        while self._sleepers and self._sleepers[0][2].done():
            heapq.heappop(self._sleepers)
        return self._sleepers[0][0] if self._sleepers else None

    async def advance(self, seconds: float) -> None:
        """Move the clock `seconds` on, each sleep that ends by then woken at its own end."""
        end = self._now + max(0.0, seconds)
        await settle()
        while (due := self.next_due) is not None and due <= end:
            _, _, woken = heapq.heappop(self._sleepers)
            self._now = max(self._now, due)
            woken.set_result(None)
            await settle()
        self._now = end
        await settle()


class TextPhrases:
    """The phrase audio of `agent`'s calls (the module's docstring)."""

    def __init__(self, agent: VoiceAgent) -> None:
        declared = {(phrase.text, phrase.language) for phrase in fixed_phrases(agent)}
        declared |= {(t, each.tag) for each in agent.languages for t in each.progress.values()}
        self.declared = declared

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        if (text, language) not in self.declared:
            raise LookupError("not a phrase declared at the start")
        return AudioChunk(pcm16=b"", sample_rate=_RATE)


class TextSide:
    """The Pipecat side of a text call (the module's docstring), on `clock`, its clauses played
    at `chars_per_second`."""

    def __init__(self, clock: Clock, *, chars_per_second: float) -> None:
        self.clock, self.chars_per_second = clock, chars_per_second
        self.speaks: dict[tuple[int, int], Speak] = {}
        self.sent: list[SessionMessage] = []
        self.overlaps: set[int] = set()
        self.ended: EndReason | None = None
        self._asked: set[tuple[int, int]] = set()
        self._dropped: set[tuple[int, int]] = set()
        self._queue: deque[Speak] = deque()
        self._waiting: deque[SessionEvent] = deque()
        self._ready = asyncio.Event()
        self._session: Session | None = None
        self._pump: asyncio.Task[None] | None = None
        self._player: asyncio.Task[None] | None = None
        self._taking = False

    def start(self, session: Session) -> None:
        """Hand every event from now on to `session`, on a task of the side's own."""
        self._session = session
        self._pump = asyncio.create_task(self._consume(session), name="text-call-events")

    def hand(self, event: SessionEvent) -> None:
        """Give the session `event`, unless io.py says it cannot come now."""
        key = (event.reply_id, event.clause) if isinstance(event, _CLAUSE_EVENTS) else None
        if key is not None and key in self._dropped:
            return
        if self.ended is not None and not isinstance(event, _REPORTS):
            return
        self._waiting.append(event)
        self._ready.set()

    def hand_all(self, events: Iterable[SessionEvent]) -> None:
        for event in events:
            self.hand(event)

    @property
    def busy(self) -> bool:
        """Whether an event waits for the session, or the session is taking one."""
        return bool(self._waiting) or self._taking

    async def run(self, command: Command) -> None:
        """Carry out `command` (the module's docstring); it never waits on the session."""
        match command:
            case Speak() if self.ended is None:
                key = (command.reply_id, command.clause)
                self.speaks[key] = command
                self._asked.add(key)
                self._queue.append(command)
                if self._player is None or self._player.done():
                    self._player = asyncio.create_task(self._play(), name="text-call-player")
            case StopSpeaking() if self.ended is None:
                self._dropped |= self._asked
                self._queue.clear()
                self._waiting = deque(e for e in self._waiting if not self._of_dropped(e))
                if self._player is not None:
                    self._player.cancel()
                    self._player = None
            case HearOverlap(turn_id=turn_id) if self.ended is None:
                self.overlaps.add(turn_id)
            case Send(message=message):
                self.sent.append(message)
            case HangUp(reason=reason):
                self.ended = reason
                self._queue.clear()
                self._waiting = deque(e for e in self._waiting if isinstance(e, _REPORTS))
            case _:
                return

    def _of_dropped(self, event: SessionEvent) -> bool:
        return isinstance(event, _CLAUSE_EVENTS) and (event.reply_id, event.clause) in self._dropped

    async def _play(self) -> None:
        """Play each clause asked for, one after another, as the fake text-to-speech says it."""
        while self._queue:
            speak = self._queue.popleft()
            reply, clause = speak.reply_id, speak.clause
            requested = None
            if speak.audio is None:
                requested = self.clock.now()
                self.hand(Synthesizing(reply_id=reply, clause=clause, at=requested))
            at = self.clock.now()
            self.hand(ClauseQueued(reply_id=reply, clause=clause, at=at, requested_at=requested))
            seconds = max(len(speak.text), 1) / self.chars_per_second
            await self.clock.sleep(seconds)
            done = ClausePlayed(
                reply_id=reply, clause=clause, at=self.clock.now(), audio_s=seconds, chunks=1
            )
            self.hand(done)

    async def _consume(self, session: Session) -> None:
        while True:
            while not self._waiting:
                self._ready.clear()
                await self._ready.wait()
            event = self._waiting.popleft()
            self._taking = True
            try:
                await session.handle(event)
            finally:
                self._taking = False

    async def aclose(self) -> None:
        """Stop the side's tasks, once the call's stream has ended."""
        for task in (self._pump, self._player):
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
