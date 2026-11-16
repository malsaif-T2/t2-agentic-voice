"""Fakes of the session's I/O (voice/session/io.py, with its events in session_events.py and
its commands in commands.py), with the port fakes in fakes.py, for the session's tests and the
Pipecat side's. Each implements one protocol of
io.py, or plays one side of it; tests/t2_agentic_voice/test_session_fakes.py checks each, and
test_session_scenes.py plays the scenes the session builds on. They live apart from fakes.py,
which would otherwise pass the 400 lines a module may hold (ARCH-SIZE):

- `FakeCommands`: where the session's commands go (`Commands`), keeping each;
- `FakeSessionIO`: the Pipecat side around a session under test: its `CallSetup`, built from
  the fakes, and every event, tap and client message, handed to the session at the fake
  clock's time, refusing one io.py says cannot come (after a stop, after the call's end, an
  overlap's part for a turn the session never marked an overlap).

A session for the Pipecat side's tests, `FakeSession`, is fake_session.py's, the phrase audio,
`FakePhrases`, fakes.py's, and the slow work that answers a turn, for the cancel scope's tests,
responder_fakes.py's.
"""

from __future__ import annotations

import json

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import EndReason, Event, TransportStage
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.voice.protocol import ClientMessage, SessionMessage, parse_client_message
from t2_agentic_voice.voice.session.commands import (
    Command,
    HangUp,
    HearOverlap,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.io import CallSetup, Session
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    CallerAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    FromClient,
    HoldResumed,
    SessionEvent,
    Synthesizing,
    Transcribed,
    Transcribing,
    TranscriptPart,
    TransportFailure,
    TurnClosed,
    TurnHeld,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeClock, FakePhrases, tone

# A call's defaults: an agent that speaks English and Saudi Arabic, a caller, and a plain
# consent, which never lets a call be recorded.
AGENT = VoiceAgent(
    name="echo-test",
    languages=[
        Language.english(greeting="Welcome to the test line"),
        Language.saudi_arabic(greeting="أهلا بك في خط التجربة"),
    ],
)
CALLER = Caller(subject="caller-1")
PLAIN_CONSENT = Consent(version=None, record_audio=False)
# A clause's events, each keyed on its reply and its index there.
CLAUSE_EVENTS = (Synthesizing, ClauseQueued, ClausePlayed, ClauseFailed)
# What the Pipecat side may still hand once the call has ended: a request's report (io.py).
REQUEST_REPORTS = (Transcribing, Synthesizing)


class FakeCommands:
    """Where a session's commands go (`Commands`): each is kept, in order, and nothing else is
    done with it."""

    def __init__(self) -> None:
        self.commands: list[Command] = []

    async def run(self, command: Command) -> None:
        self.commands.append(command)

    def of[C](self, kind: type[C]) -> list[C]:
        """The commands of `kind`, in order."""
        return [command for command in self.commands if isinstance(command, kind)]

    @property
    def sent(self) -> list[SessionMessage]:
        """The messages the session sent the client, in order."""
        return [command.message for command in self.of(Send)]


class FakeSessionIO:
    """The Pipecat side around a session under test. `setup` is the call's `CallSetup`, built
    from the fakes: the `agent`, `caller` and `consent` given, the call's language as join
    fixes it from `language` (the caller's pick) and the caller's locale, `settings`, `phrases`
    (the agent's own by default), `max_chars` for every language, tracing off, the public
    events kept in `emitted`, and `clock`. `commands` keeps what the session gives. Once
    `attach`ed to a session, each method below builds its event at the clock's time, keeps it
    in `events`, hands it to the session, and returns it. It refuses, with RuntimeError, what
    io.py says cannot come: an event of a clause a `StopSpeaking` dropped; an overlap's
    `window` or `overlap` part for a turn the session gave no `HearOverlap` for; once the call
    has ended (an `Ending` or a `TransportFailure` handed, or a `HangUp` given), any event but
    a request's report (`Transcribing`, `Synthesizing`); and any event once `close` has ended
    the call's stream."""

    def __init__(
        self,
        settings: VoiceSettings,
        *,
        agent: VoiceAgent = AGENT,
        caller: Caller = CALLER,
        consent: Consent = PLAIN_CONSENT,
        language: LanguageTag | None = None,
        phrases: FakePhrases | None = None,
        max_chars: int | None = 200,
        clock: FakeClock | None = None,
        call_id: str = "call-1",
    ) -> None:
        self.clock = clock or FakeClock()
        self.phrases = phrases or FakePhrases.of(agent)
        self.commands = FakeCommands()
        self.emitted: list[Event] = []
        self.events: list[SessionEvent] = []
        self.closed = False
        self.setup = CallSetup(
            call_id=call_id,
            caller=caller,
            consent=consent,
            agent=agent,
            language=agent.call_language(language, locale=caller.locale),
            settings=settings,
            phrases=self.phrases,
            max_chars=lambda language: max_chars,
            tracing=Tracing(),
            emit=self.emitted.append,
            clock=self.clock,
        )
        self._session: Session | None = None

    def attach(self, session: Session) -> None:
        """Hand every event from now on to `session`."""
        self._session = session

    @property
    def ended(self) -> bool:
        """Whether the call has ended: an `Ending` or a `TransportFailure` was handed, or the
        session gave its `HangUp`."""
        last = (Ending, TransportFailure)
        return any(isinstance(e, last) for e in self.events) or bool(self.commands.of(HangUp))

    @property
    def overlaps(self) -> set[int]:
        """The turns the session marked an overlap (`HearOverlap`)."""
        return {command.turn_id for command in self.commands.of(HearOverlap)}

    @property
    def dropped(self) -> set[tuple[int, int]]:
        """The clauses a `StopSpeaking` dropped, by reply and index: every one the session had
        asked for before its last stop, whatever its reply."""
        asked: list[tuple[int, int]] = []
        dropped: set[tuple[int, int]] = set()
        for command in self.commands.commands:
            if isinstance(command, Speak):
                asked.append((command.reply_id, command.clause))
            elif isinstance(command, StopSpeaking):
                dropped = set(asked)
        return dropped

    def _refusal(self, event: SessionEvent) -> str | None:
        """Why io.py says `event` cannot come now, with its FIX; None when it can."""
        if self.closed:
            return "the call's stream has ended. FIX: end the scene at `close`."
        if self.ended and not isinstance(event, REQUEST_REPORTS):
            return (
                "the call has ended, and only a request's report follows its end. FIX: end the "
                "scene at its Ending, its TransportFailure or the session's HangUp."
            )
        if isinstance(event, CLAUSE_EVENTS) and (event.reply_id, event.clause) in self.dropped:
            return "a stop dropped the clause. FIX: hand no event of a clause a stop dropped."
        if (
            isinstance(event, Transcribing | Transcribed)
            and event.part in ("window", "overlap")
            and event.turn_id not in self.overlaps
        ):
            return "no HearOverlap marked the turn an overlap. FIX: let the session give it first."
        return None

    async def _hand[E: SessionEvent](self, event: E) -> E:
        if self._session is None:
            raise RuntimeError("no session to hand the event to. FIX: attach one first.")
        refusal = self._refusal(event)
        if refusal is not None:
            raise RuntimeError(f"no such event can come (io.py): {refusal}")
        self.events.append(event)
        await self._session.handle(event)
        return event

    async def close(self) -> None:
        """End the call's stream, as the Pipecat side does once the call has ended and it has
        handed the last request's report: the session's `aclose`; no event follows."""
        if self._session is None or not self.ended:
            raise RuntimeError(
                "the stream ends only after the call. FIX: hand its Ending or its "
                "TransportFailure, or let the session give its HangUp, first."
            )
        self.closed = True
        await self._session.aclose()

    async def connected(self) -> Connected:
        return await self._hand(Connected(at=self.clock.now()))

    async def turn_opened(self, turn_id: int, *, speech_at: float | None = None) -> TurnOpened:
        """The turn opens now; its speech began at `speech_at` (by default, now)."""
        now = self.clock.now()
        began = now if speech_at is None else speech_at
        return await self._hand(TurnOpened(turn_id=turn_id, at=now, speech_at=began))

    async def turn_held(self, turn_id: int) -> TurnHeld:
        """The turn's hold began now (the early start's)."""
        return await self._hand(TurnHeld(turn_id=turn_id, at=self.clock.now()))

    async def hold_resumed(self, turn_id: int) -> HoldResumed:
        """The caller spoke again within the turn's hold, now."""
        return await self._hand(HoldResumed(turn_id=turn_id, at=self.clock.now()))

    async def turn_closed(
        self, turn_id: int, *, speech_ended_at: float | None = None
    ) -> TurnClosed:
        """The turn closes now; its speech stopped at `speech_ended_at` (by default, now)."""
        now = self.clock.now()
        ended = now if speech_ended_at is None else speech_ended_at
        return await self._hand(TurnClosed(turn_id=turn_id, at=now, speech_ended_at=ended))

    async def transcribing(
        self, turn_id: int, *, audio_s: float = 1.0, part: TranscriptPart = "turn"
    ) -> Transcribing:
        """The turn's request of `part` goes now, with `audio_s` of its audio, as the bridge
        sends it."""
        now = self.clock.now()
        event = Transcribing(turn_id=turn_id, at=now, audio_s=audio_s, part=part)
        return await self._hand(event)

    async def transcribed(
        self,
        turn_id: int,
        text: str | None,
        *,
        language: str | None = None,
        failure: ProviderErrorKind | None = None,
        retryable: bool = False,
        part: TranscriptPart = "turn",
        switched: bool = False,
    ) -> Transcribed:
        """The turn's transcript of `part`, `text` heard in `language` (a detecting request's,
        moving the call, when `switched`), its request's audio billed as Groq bills it; or
        None, with `failure` when the request failed and with no request otherwise. A request
        that went is the turn's last `Transcribing` of `part`, which gives the result its audio
        and when it went, or for the `turn` part of an overlap's turn with none of its own, the
        overlap's, whose transcript it reuses; for an
        `overlap` part with none of its own (its `HearOverlap` reached the bridge after the turn
        closed), the turn's: RuntimeError when none was handed."""
        sent = self._sent(turn_id, part)
        if not sent and part == "turn":
            sent = self._sent(turn_id, "overlap") or self._sent(turn_id, "held")
        elif not sent and part == "overlap":
            sent = self._sent(turn_id, "turn")
        if (text is not None or failure) and not sent:
            raise RuntimeError(
                "the turn's request went with no Transcribing (io.py's usage). FIX: hand it "
                "first, with `transcribing`."
            )
        audio_s = sent[-1].audio_s if sent else 0.0
        transcript = None
        if text is not None:
            billed = max(10.0, audio_s)
            transcript = Transcript(text=text, language=language, billed_seconds=billed)
        event = Transcribed(
            turn_id=turn_id,
            at=self.clock.now(),
            audio_s=audio_s,
            sent_at=sent[-1].at if sent else None,
            transcript=transcript,
            failure=failure,
            retryable=retryable,
            part=part,
            switched=switched,
        )
        return await self._hand(event)

    def _sent(self, turn_id: int, part: TranscriptPart) -> list[Transcribing]:
        """The turn's requests of `part` handed so far, in order."""
        found = (e for e in self.events if isinstance(e, Transcribing) and e.turn_id == turn_id)
        return [e for e in found if e.part == part]

    async def synthesizing(self, reply_id: int, clause: int) -> Synthesizing:
        """The clause's text-to-speech request goes now."""
        now = self.clock.now()
        return await self._hand(Synthesizing(reply_id=reply_id, clause=clause, at=now))

    async def clause_queued(
        self, reply_id: int, clause: int, *, held: bool = False
    ) -> ClauseQueued:
        """The clause's first audio is queued now: its request went at its `Synthesizing`, or
        none did (a cached phrase, or a take the clause cache held: `held`)."""
        asked = [e for e in self.events if isinstance(e, Synthesizing)]
        sent = [e.at for e in asked if (e.reply_id, e.clause) == (reply_id, clause)]
        requested_at, now = (sent[-1] if sent else None), self.clock.now()
        event = ClauseQueued(
            reply_id=reply_id, clause=clause, at=now, requested_at=requested_at, held=held
        )
        return await self._hand(event)

    async def clause_played(
        self,
        reply_id: int,
        clause: int,
        *,
        audio_s: float = 1.0,
        chunks: int = 1,
        remaining: tuple[int | None, int | None] = (None, None),
        cut_short: bool = False,
    ) -> ClausePlayed:
        """The clause played `audio_s` in `chunks`, its response reporting `remaining`
        (requests, tokens: none for a cached phrase) and maybe cut short."""
        requests, tokens = remaining
        event = ClausePlayed(
            reply_id=reply_id,
            clause=clause,
            at=self.clock.now(),
            audio_s=audio_s,
            chunks=chunks,
            remaining_requests=requests,
            remaining_tokens=tokens,
            cut_short=cut_short,
        )
        return await self._hand(event)

    async def clause_failed(
        self, reply_id: int, clause: int, *, failure: ProviderErrorKind = "timeout"
    ) -> ClauseFailed:
        retryable = failure != "rejected"
        now = self.clock.now()
        event = ClauseFailed(
            reply_id=reply_id, clause=clause, at=now, failure=failure, retryable=retryable
        )
        return await self._hand(event)

    async def caller_audio(self, seconds: float, *, sample_rate: int = 16_000) -> CallerAudio:
        """The input tap: `seconds` of the caller's audio (the fakes' tone)."""
        audio, now = tone(seconds, sample_rate), self.clock.now()
        return await self._hand(CallerAudio(pcm16=audio, sample_rate=sample_rate, at=now))

    async def agent_audio(self, seconds: float, *, sample_rate: int = 24_000) -> AgentAudio:
        """The output tap: `seconds` of the agent's audio (the fakes' tone)."""
        audio, now = tone(seconds, sample_rate), self.clock.now()
        return await self._hand(AgentAudio(pcm16=audio, sample_rate=sample_rate, at=now))

    async def client(self, message: object) -> FromClient:
        """A client's message: a `t2v/1` model, an object as Pipecat hands it on, or the text
        the data channel carried, parsed as a call's path parses it: `json.loads`, as Pipecat
        does (ValueError for text that is not JSON, which Pipecat drops), then the object path,
        so a key the text held twice gives its last value. InvalidRequestError for anything
        that is not exactly one of `t2v/1`'s, which the Pipecat side drops."""
        if isinstance(message, str | bytes):
            message = json.loads(message)
        parsed: ClientMessage = (
            message if isinstance(message, ClientMessage) else parse_client_message(message)
        )
        return await self._hand(FromClient(message=parsed, at=self.clock.now()))

    async def transport_failure(self, stage: TransportStage = "media") -> TransportFailure:
        return await self._hand(TransportFailure(stage=stage, at=self.clock.now()))

    async def ending(self, reason: EndReason = "caller_left") -> Ending:
        return await self._hand(Ending(reason=reason, at=self.clock.now()))
