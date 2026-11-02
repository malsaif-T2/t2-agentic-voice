"""Fakes of the session's I/O (voice/session/io.py, with its events in session_events.py and
its commands in commands.py), with the port fakes in fakes.py, for the session's tests (Track D)
and the Pipecat side's (Track E). Each implements one protocol of io.py, or plays one side of
it; tests/t2_agentic_voice/test_session_fakes.py checks each. They live apart from fakes.py,
which would otherwise pass the 400 lines a module may hold (ARCH-SIZE):

- `FakePhrases`: the runtime's fixed phrases' audio (`PhraseAudio`), refusing any text not
  declared;
- `FakeCommands`: where the session's commands go (`Commands`), keeping each;
- `FakeSession`: a session (`Session`) for the Pipecat side, built as `CallSession` is;
- `FakeSessionIO`: the Pipecat side around a session under test: its `CallSetup`, built from
  the fakes, and every event, tap and client message, handed to the session at the fake
  clock's time, none after the call's end (io.py's end).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import EndReason, Event, TransportStage
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import ClientMessage, SessionMessage, parse_client_message
from t2_agentic_voice.voice.session.commands import Command, HangUp, Send
from t2_agentic_voice.voice.session.io import CallSetup, Commands, Session
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    CallerAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    FromClient,
    SessionEvent,
    Transcribed,
    TransportFailure,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeClock, tone

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


class FakePhrases:
    """The runtime's fixed phrases' audio (`PhraseAudio`): each text declared in its language,
    said as `seconds` of the fakes' tone at `sample_rate`; LookupError for any other, as the
    phrase cache refuses text not declared at the start. Every text asked for is kept, found or
    not (`asked`), so a test can tell that no heard words reached the cache."""

    def __init__(
        self,
        declared: Iterable[tuple[str, LanguageTag]] = (),
        *,
        seconds: float = 0.5,
        sample_rate: int = 24_000,
    ) -> None:
        self.declared = set(declared)
        self.seconds = seconds
        self.sample_rate = sample_rate
        self.asked: list[tuple[str, LanguageTag]] = []

    @classmethod
    def of(cls, agent: VoiceAgent) -> FakePhrases:
        """The phrases `agent` declares: each language's greeting and echo frame."""
        return cls(
            (text, language.tag)
            for language in agent.languages
            for text in (language.greeting, language.echo_frame)
        )

    def audio(self, text: str, *, language: LanguageTag) -> AudioChunk:
        self.asked.append((text, language))
        if (text, language) not in self.declared:
            raise LookupError("not a phrase declared at the start")
        return AudioChunk(pcm16=tone(self.seconds, self.sample_rate), sample_rate=self.sample_rate)


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


class FakeSession:
    """A session (`Session`) for the Pipecat side's tests, built as `CallSession` is, from a
    call's setup and where its commands go: it keeps every event handed to it, and for each
    gives the commands `replies` returns for it, in order (none by default). A test gives a
    command of its own with `give`."""

    def __init__(
        self,
        setup: CallSetup,
        commands: Commands,
        *,
        replies: Callable[[SessionEvent], Sequence[Command]] = lambda event: (),
    ) -> None:
        self.setup = setup
        self.commands = commands
        self.replies = replies
        self.events: list[SessionEvent] = []

    async def handle(self, event: SessionEvent) -> None:
        self.events.append(event)
        for command in self.replies(event):
            await self.commands.run(command)

    async def give(self, command: Command) -> None:
        await self.commands.run(command)


class FakeSessionIO:
    """The Pipecat side around a session under test. `setup` is the call's `CallSetup`, built
    from the fakes: the `agent`, `caller` and `consent` given, the call's language as join
    fixes it from `language` (the caller's pick) and the caller's locale, `settings`, `phrases`
    (the agent's own by default), `max_chars` for every language, tracing off, the public
    events kept in `emitted`, and `clock`. `commands` keeps what the session gives. Once
    `attach`ed to a session, each method below builds its event at the clock's time, keeps it
    in `events`, hands it to the session, and returns it; none once the call has ended (an
    `Ending` or a `TransportFailure` handed, or a `HangUp` given), which raises RuntimeError,
    as no event follows the end (io.py)."""

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

    async def _hand[E: SessionEvent](self, event: E) -> E:
        if self._session is None:
            raise RuntimeError("no session to hand the event to. FIX: attach one first.")
        if self.ended:
            raise RuntimeError(
                "the call has ended, and no event follows its end (io.py). FIX: end the scene "
                "at its Ending, its TransportFailure or the session's HangUp."
            )
        self.events.append(event)
        await self._session.handle(event)
        return event

    async def connected(self) -> Connected:
        return await self._hand(Connected(at=self.clock.now()))

    async def turn_opened(self, turn_id: int, *, speech_at: float | None = None) -> TurnOpened:
        """The turn opens now; its speech began at `speech_at` (by default, now)."""
        now = self.clock.now()
        began = now if speech_at is None else speech_at
        return await self._hand(TurnOpened(turn_id=turn_id, at=now, speech_at=began))

    async def turn_closed(
        self, turn_id: int, *, speech_ended_at: float | None = None
    ) -> TurnClosed:
        """The turn closes now; its speech stopped at `speech_ended_at` (by default, now)."""
        now = self.clock.now()
        ended = now if speech_ended_at is None else speech_ended_at
        return await self._hand(TurnClosed(turn_id=turn_id, at=now, speech_ended_at=ended))

    async def transcribed(
        self,
        turn_id: int,
        text: str | None,
        *,
        language: str | None = None,
        audio_s: float = 1.0,
        failure: ProviderErrorKind | None = None,
        retryable: bool = False,
    ) -> Transcribed:
        """The turn's transcript, `text` heard in `language`, its `audio_s` billed as Groq
        bills; or None, with `failure` when the request failed and with no request otherwise.
        A request went when the turn closed (as the bridge sends it), or now if it has not."""
        now = self.clock.now()
        transcript = None
        if text is not None:
            billed = max(10.0, audio_s)
            transcript = Transcript(text=text, language=language, billed_seconds=billed)
        closed = [e.at for e in self.events if isinstance(e, TurnClosed) and e.turn_id == turn_id]
        event = Transcribed(
            turn_id=turn_id,
            at=now,
            audio_s=audio_s,
            sent_at=(closed or [now])[-1] if failure or transcript else None,
            transcript=transcript,
            failure=failure,
            retryable=retryable,
        )
        return await self._hand(event)

    async def clause_queued(
        self, reply_id: int, clause: int, *, requested_at: float | None = None
    ) -> ClauseQueued:
        now = self.clock.now()
        event = ClauseQueued(reply_id=reply_id, clause=clause, at=now, requested_at=requested_at)
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
        audio = tone(seconds, sample_rate)
        return await self._hand(
            CallerAudio(pcm16=audio, sample_rate=sample_rate, at=self.clock.now())
        )

    async def agent_audio(self, seconds: float, *, sample_rate: int = 24_000) -> AgentAudio:
        """The output tap: `seconds` of the agent's audio (the fakes' tone)."""
        audio = tone(seconds, sample_rate)
        return await self._hand(
            AgentAudio(pcm16=audio, sample_rate=sample_rate, at=self.clock.now())
        )

    async def client(self, message: object) -> FromClient:
        """A client's message: a `t2v/1` model, or the object or JSON text the transport
        carried, parsed as the Pipecat side parses it (InvalidRequestError for anything else)."""
        parsed: ClientMessage = (
            message if isinstance(message, ClientMessage) else parse_client_message(message)
        )
        return await self._hand(FromClient(message=parsed, at=self.clock.now()))

    async def transport_failure(self, stage: TransportStage = "media") -> TransportFailure:
        return await self._hand(TransportFailure(stage=stage, at=self.clock.now()))

    async def ending(self, reason: EndReason = "caller_left") -> Ending:
        return await self._hand(Ending(reason=reason, at=self.clock.now()))
