"""The session bridge: where one call's Pipecat pipeline meets its session (voice/session/io.py),
a plain `FrameProcessor` between the speech-to-text bridge and the text-to-speech bridge (the
design's 13; plan 003's appendix, "Changes to the plan's interfaces", items 3 and 7).

- `CallEvents` is the call's stream of session events. Every Pipecat module of the call (the
  bridges, the transport's taps, its connection) hands each event here as it happens, and one
  task gives them to `Session.handle`, one at a time, in that order, so no module waits on the
  session. It holds what io.py says cannot come: an event of a clause a `StopSpeaking` dropped
  (one already waiting for the session included, a request's report too: TD-055), and, once the
  call has ended, any event but a request's report. `close` ends the stream with the session's
  `aclose` once the last waiting event is handed.
- `SessionBridge` hands the session each client message the transport parsed (its
  `InputTransportMessageFrame`, the object Pipecat's `on_app_message` gives, voice/protocol.py's
  object path), dropping, with a log line that holds none of it, one that is not `t2v/1`'s.
- `SessionCommands` carries out the session's commands, in order: `ListenIn` names the
  speech-to-text bridge's language; `Speak` sends the clause downstream to the text-to-speech
  bridge (`SpeakFrame`); `StopSpeaking` drops every clause asked for so far and broadcasts
  Pipecat's interruption from here, upstream of the text-to-speech bridge, so every processor
  drops its queued frames; `Send` hands the message to the output transport at once, ahead of
  any queued audio and never dropped by a stop; and `HangUp` ends the call.

A clause is keyed on its reply and its index (`ClauseKey`), and its text-to-speech context is
named from that key (`context_id`), so the output's frames say whose audio they carry.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pipecat.frames.frames import DataFrame, Frame, InputTransportMessageFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from t2_agentic_voice.core.errors import InvalidRequestError
from t2_agentic_voice.core.events import EndReason
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.protocol import parse_client_message, wire
from t2_agentic_voice.voice.session.commands import (
    Command,
    HangUp,
    ListenIn,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.io import Clock, Session
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Ending,
    FromClient,
    SessionEvent,
    Synthesizing,
    Transcribing,
    TransportFailure,
)

log = get_logger(__name__)

# A clause of the agent's: its reply and its index there (voice/session/io.py's replies).
ClauseKey = tuple[int, int]
_CONTEXT_PREFIX = "t2v-clause-"
# What may still be handed once the call has ended: a request's report (io.py's end).
_REPORTS = (Transcribing, Synthesizing)
_CLAUSE_EVENTS = (Synthesizing, ClauseQueued, ClausePlayed, ClauseFailed)
# How long `close` waits for the session to take the events still waiting, and to finish
# (`aclose` writes the call's report): the agent's bound, so no call's end hangs on it.
CLOSE_WAIT_S = 10.0


def context_id(key: ClauseKey) -> str:
    """The text-to-speech context of the clause `key`."""
    return f"{_CONTEXT_PREFIX}{key[0]}-{key[1]}"


def clause_of(context: str | None) -> ClauseKey | None:
    """The clause whose context `context` is; None for any other."""
    if not context or not context.startswith(_CONTEXT_PREFIX):
        return None
    reply, _, clause = context.removeprefix(_CONTEXT_PREFIX).partition("-")
    return int(reply), int(clause)


@dataclass
class SpeakFrame(DataFrame):
    """A clause the session asked for (its `Speak`), on its way to the text-to-speech bridge;
    interruptible, so a stop drops it wherever it waits."""

    speak: Speak


@dataclass
class ClauseEndFrame(DataFrame):
    """Marks, at its place in the output, a clause whose audio is empty: it passes the
    text-to-speech bridge behind the audio queued before it, and the output transport behind
    the audio it has still to send (io.py's replies)."""

    key: ClauseKey


def _key(event: SessionEvent) -> ClauseKey | None:
    return (event.reply_id, event.clause) if isinstance(event, _CLAUSE_EVENTS) else None


class CallEvents:
    """One call's stream of session events, handed to its session in the order they happened.
    `asked` holds every clause the session asked for, `dropped` those a stop dropped; `ended`
    says whether the call has ended. With `record`, `handed` keeps every event the session was
    given, in order, and `watch`, when set, sees each as it is given (the file-fed transport's
    `FedCall`, and its watch for the greeting's end)."""

    def __init__(self, clock: Clock, *, record: bool = False) -> None:
        self.clock = clock
        self.asked: set[ClauseKey] = set()
        self.dropped: set[ClauseKey] = set()
        self.ended = False
        self.closed = False
        self.handed: list[SessionEvent] | None = [] if record else None
        self.watch: Callable[[SessionEvent], None] | None = None
        self._waiting: deque[SessionEvent] = deque()
        self._ready = asyncio.Event()
        self._session: Session | None = None
        self._consumer: asyncio.Task[None] | None = None
        self._closing = False

    def start(self, session: Session) -> None:
        """Hand every event from now on to `session`, on a task of the stream's own."""
        self._session = session
        self._consumer = asyncio.create_task(self._consume(session), name="t2v-call-events")

    def hand(self, event: SessionEvent) -> None:
        """Give the session `event`, unless io.py says it cannot come now. An `Ending` or a
        `TransportFailure` ends the call: what follows it is only a request's report."""
        key = _key(event)
        if self.closed or (key is not None and key in self.dropped):
            return
        if self.ended and not isinstance(event, _REPORTS):
            return
        self._waiting.append(event)
        self._ready.set()
        if isinstance(event, Ending | TransportFailure):
            self.ended = True

    def stop_speaking(self) -> None:
        """Drop every clause asked for so far, and every event of one still waiting."""
        self.dropped |= self.asked
        self._waiting = deque(e for e in self._waiting if _key(e) not in self.dropped)

    def end(self) -> None:
        """The session hung up: from now on, and of what is waiting, only a request's report
        is handed."""
        self.ended = True
        self._waiting = deque(e for e in self._waiting if isinstance(e, _REPORTS))

    async def close(self) -> None:
        """End the call's stream: once the events waiting are handed, the session's `aclose`,
        then nothing more. Each step is bounded (`CLOSE_WAIT_S`)."""
        self.ended = self._closing = True
        self._ready.set()
        if self._consumer is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._consumer), CLOSE_WAIT_S)
            except TimeoutError:
                log.error("call_events_close_timeout", waited_s=CLOSE_WAIT_S)
                self._consumer.cancel()
        self.closed = True
        if self._session is not None:
            try:
                await asyncio.wait_for(self._session.aclose(), CLOSE_WAIT_S)
            except Exception as error:  # the session never raises; a timeout is ours
                log.error("session_close_failed", error=type(error).__name__)

    async def _consume(self, session: Session) -> None:
        while True:
            while not self._waiting:
                if self._closing:
                    return
                self._ready.clear()
                await self._ready.wait()
            event = self._waiting.popleft()
            if self.handed is not None:
                self.handed.append(event)
            if self.watch is not None:
                self.watch(event)
            try:
                await session.handle(event)
            except Exception as error:  # the session never raises (io.py); keep the stream
                log.error(
                    "session_event_failed", kind=type(event).__name__, error=type(error).__name__
                )


class SessionBridge(FrameProcessor):
    """The plain processor between the speech-to-text bridge and the text-to-speech bridge: it
    hands the session each client message, and passes every other frame on."""

    def __init__(self, events: CallEvents) -> None:
        super().__init__(name="t2v-session-bridge")
        self._events = events

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputTransportMessageFrame):
            if direction == FrameDirection.DOWNSTREAM:
                self._from_client(frame.message)
            return
        await self.push_frame(frame, direction)

    def _from_client(self, message: object) -> None:
        try:
            parsed = parse_client_message(message)
        except InvalidRequestError as error:
            log.info("client_message_dropped", problems=error.details.get("problems"))
            return
        self._events.hand(FromClient(message=parsed, at=self._events.clock.now()))


class SessionCommands:
    """Where the session's commands go (io.py's `Commands`): each carried out after every one
    before it, never raising. `listen` names the speech-to-text bridge's language, `send` hands
    a message to the output transport, and `hang_up` ends the call. With `record`, `given`
    keeps every command with when it came, on the call's clock (the file-fed transport's
    `FedCall`)."""

    def __init__(
        self,
        bridge: SessionBridge,
        events: CallEvents,
        *,
        listen: Callable[[str | None], None],
        send: Callable[[object], Awaitable[None]],
        hang_up: Callable[[EndReason], None],
        record: bool = False,
    ) -> None:
        self._bridge = bridge
        self._events = events
        self._listen = listen
        self._send = send
        self._hang_up = hang_up
        self._lock = asyncio.Lock()
        self.given: list[tuple[float, Command]] | None = [] if record else None

    async def run(self, command: Command) -> None:
        async with self._lock:
            if self.given is not None:
                self.given.append((self._events.clock.now(), command))
            try:
                await self._carry_out(command)
            except Exception as error:  # what fails comes back as an event, never raised
                log.error(
                    "command_failed", command=type(command).__name__, error=type(error).__name__
                )

    async def _carry_out(self, command: Command) -> None:
        events = self._events
        match command:
            case ListenIn(language=language):
                self._listen(language)
            case Speak(reply_id=reply, clause=clause) if not events.ended:
                events.asked.add((reply, clause))
                await self._bridge.push_frame(SpeakFrame(speak=command))
            case StopSpeaking() if not events.ended:
                events.stop_speaking()
                interrupt: Callable[[], Awaitable[None]] = self._bridge.broadcast_interruption
                await interrupt()
            case Send(message=message):  # the `ended` message comes after an `Ending` too
                await self._send(wire(message))
            case HangUp(reason=reason):
                events.end()
                self._hang_up(reason)
            case _:  # a command after the call's end: io.py says none comes
                log.debug("command_after_end", command=type(command).__name__)
