"""The fakes of the session's I/O (tests/t2_agentic_voice/session_fakes.py, fake_session.py, and
fakes.py's phrase audio) implement their protocols of voice/session/io.py, so the session and the
Pipecat side build against the real interfaces: each is assigned to its protocol, which mypy
checks, and does what its docstring says, refusing what io.py says cannot come; the fake
session holds its lock as the real one does, so a `Commands.run` that calls it back or waits
fails (TD-068); and the slow work that answers a turn (responder_fakes.py) is held mid-flight on
the fake clock and cancelled there. The scenes the session builds on are
test_session_scenes.py's."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from t2_agentic_voice import InvalidRequestError
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.fixed_phrases import fixed_phrases
from t2_agentic_voice.events import CallStarted
from t2_agentic_voice.voice.protocol import Hangup, State, Stop
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import (
    COMMANDS,
    Command,
    HangUp,
    HearOverlap,
    ListenIn,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.io import CallSetup, Commands, PhraseAudio, Session
from t2_agentic_voice.voice.session.session_events import (
    SESSION_EVENTS,
    ClausePlayed,
    ClauseQueued,
    Connected,
    FromClient,
    SessionEvent,
    Synthesizing,
    Transcribed,
    Transcribing,
    TransportFailure,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fake_session import RUN_S, FakeSession
from tests.t2_agentic_voice.fakes import FakeClock, FakePhrases
from tests.t2_agentic_voice.responder_fakes import CHUNKS, SlowResponder
from tests.t2_agentic_voice.session_fakes import (
    AGENT,
    CALLER,
    PLAIN_CONSENT,
    FakeCommands,
    FakeSessionIO,
)

# A playback report as the channel carries it.
PLAYED = '{"v": 1, "type": "playback", "reply_id": 1, "clause": 0, "event": "ended"}'
# Every command of commands.py, one of each kind.
ONE_OF_EACH: list[Command] = [
    ListenIn(language="en"),
    HearOverlap(turn_id=0, window_ms=750),
    Speak(reply_id=1, clause=0, turn_id=0, text="a clause for the test", language="en"),
    StopSpeaking(reply_id=1),
    Send(message=State(state="listening")),
    HangUp(reason="hangup"),
]


def test_one_of_each_command_is_every_command() -> None:
    assert [type(c) for c in ONE_OF_EACH] == list(COMMANDS)


def test_the_fake_phrases_give_only_the_phrases_declared() -> None:
    fake = FakePhrases.of(AGENT)
    phrases: PhraseAudio = fake
    english, arabic = AGENT.languages
    chunk = phrases.audio(english.greeting, language="en")
    assert (chunk.seconds, chunk.sample_rate) == (0.5, 24_000)
    assert phrases.audio(arabic.echo_frame, language="ar-SA").pcm16 == chunk.pcm16
    missing: list[tuple[str, LanguageTag]] = [
        (english.greeting, "ar-SA"),
        ("words heard in a call", "en"),
    ]
    for text, language in missing:
        with pytest.raises(LookupError):
            phrases.audio(text, language=language)
    assert fake.asked[-1] == ("words heard in a call", "en") and len(fake.asked) == 4
    assert fake.declared == {(phrase.text, phrase.language) for phrase in fixed_phrases(AGENT)}
    assert phrases.audio(english.notices["ended"], language="en").pcm16 == chunk.pcm16
    with pytest.raises(LookupError):
        phrases.audio(english.notices["busy"], language="en")  # spoken by no call


def test_the_fake_commands_keep_each_command() -> None:
    fake = FakeCommands()
    commands: Commands = fake

    async def run_all() -> None:
        for command in ONE_OF_EACH:
            await commands.run(command)

    asyncio.run(run_all())
    assert fake.commands == ONE_OF_EACH
    assert fake.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert fake.sent == [State(state="listening")]


def test_the_fake_session_is_built_and_driven_as_the_call_session_is(
    settings: VoiceSettings,
) -> None:
    io = FakeSessionIO(settings)
    build: Callable[[CallSetup, Commands], Session] = FakeSession
    build = CallSession  # the real one's shape, which a Pipecat side's factory takes
    hello = Send(message=State(state="listening"))

    def replies(event: SessionEvent) -> list[Command]:
        return [hello] if isinstance(event, TurnOpened) else []

    session = FakeSession(io.setup, io.commands, replies=replies)
    io.attach(session)

    async def drive() -> None:
        await io.connected()
        await io.turn_opened(0)
        with pytest.raises(RuntimeError, match="FIX: "):  # the call has not ended
            await io.close()
        await session.give(HangUp(reason="hangup"))
        with pytest.raises(RuntimeError, match="FIX: "):  # no event follows the HangUp
            await io.turn_closed(0)
        assert not session.closed
        await io.close()

    asyncio.run(drive())
    assert session.events == io.events and session.setup is io.setup and build is CallSession
    assert io.commands.commands == [hello, HangUp(reason="hangup")] and io.ended
    assert session.closed and io.closed


def test_the_fake_io_builds_the_calls_setup_from_the_fakes(settings: VoiceSettings) -> None:
    clock = FakeClock(start=5.0)
    io = FakeSessionIO(settings, clock=clock, max_chars=None, call_id="call-9")
    setup = io.setup
    assert (setup.call_id, setup.caller, setup.consent, setup.agent) == (
        "call-9",
        CALLER,
        PLAIN_CONSENT,
        AGENT,
    )
    assert (setup.settings, setup.phrases, setup.clock) == (settings, io.phrases, clock)
    assert (setup.max_chars("en"), FakeSessionIO(settings).setup.max_chars("ar")) == (None, 200)
    with setup.tracing.turn(session_id="call-9") as span:
        assert not span.is_recording()  # tracing off
    started = CallStarted(call_id="call-9", at=clock.wall())
    setup.emit(started)
    assert io.emitted == [started]


def test_the_fake_io_fixes_the_calls_language_as_join_does(settings: VoiceSettings) -> None:
    """The agent's first language with nothing to pick another; the caller's pick; the locale."""
    saudi = Caller(subject="caller-2", locale="ar-SA")
    languages = [
        FakeSessionIO(settings).setup.language,
        FakeSessionIO(settings, language="ar-SA").setup.language,
        FakeSessionIO(settings, caller=saudi).setup.language,
        FakeSessionIO(settings, caller=saudi, language="en").setup.language,
    ]
    assert [language.tag for language in languages] == ["en", "ar-SA", "ar-SA", "en"]
    assert all(language in AGENT.languages for language in languages)


def test_the_fake_io_hands_a_session_every_event_at_the_clocks_time(
    settings: VoiceSettings,
) -> None:
    io = FakeSessionIO(settings)
    session = FakeSession(io.setup, io.commands)

    async def call() -> None:
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.connected()
        io.attach(session)
        await io.connected()
        await io.turn_opened(0, speech_at=99.5)
        await io.caller_audio(0.02)
        await io.clock.advance(1.5)
        await io.turn_closed(0, speech_ended_at=101.0)
        await io.transcribing(0, audio_s=1.4)
        await io.clock.advance(0.5)
        await io.transcribed(0, "words of the test", language="en")
        await io.turn_opened(1)
        with pytest.raises(RuntimeError, match="FIX: "):  # a failure, yet no request went
            await io.transcribed(1, None, failure="timeout", retryable=True)
        await io.transcribing(1)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await io.transcribed(2, None)  # nothing to send
        await io.synthesizing(1, 0)
        await io.clock.advance(0.25)
        await io.clause_queued(1, 0)
        await io.clause_queued(1, 1)  # a cached phrase: no request
        await io.agent_audio(0.04)
        await io.clause_played(1, 0, audio_s=0.6, chunks=3, remaining=(9, 900), cut_short=True)
        await io.clause_failed(1, 1, failure="rejected")
        await io.client({"v": 1, "type": "hangup"})
        await io.client(PLAYED)
        await io.client(Hangup(v=1, type="hangup"))
        with pytest.raises(InvalidRequestError):
            await io.client({"v": 1, "type": "hangup", "consent": True})
        await io.ending()

    asyncio.run(call())
    assert session.events == io.events
    assert {type(event) for event in io.events} == set(SESSION_EVENTS) - {TransportFailure}
    opened, _, closed, sent, heard, other = io.events[1:7]
    assert isinstance(opened, TurnOpened) and (opened.at, opened.speech_at) == (100.0, 99.5)
    assert isinstance(closed, TurnClosed) and (closed.at, closed.speech_ended_at) == (101.5, 101.0)
    assert isinstance(sent, Transcribing) and (sent.turn_id, sent.at, sent.audio_s) == (
        0,
        101.5,
        1.4,
    )
    assert isinstance(heard, Transcribed) and heard.transcript is not None
    assert (heard.at, heard.sent_at, heard.audio_s) == (102.0, 101.5, 1.4)
    assert (heard.transcript.text, heard.transcript.billed_seconds) == ("words of the test", 10.0)
    assert isinstance(other, TurnOpened) and other.speech_at == other.at == 102.0
    failed, nothing = (e for e in io.events if isinstance(e, Transcribed) and e.turn_id)
    assert (failed.failure, failed.sent_at, failed.audio_s) == ("timeout", 102.0, 1.0)
    assert (nothing.transcript, nothing.sent_at, nothing.audio_s) == (None, None, 0.0)
    queued = [e for e in io.events if isinstance(e, ClauseQueued)]
    assert [(e.at, e.requested_at) for e in queued] == [(102.25, 102.0), (102.25, None)]
    (played,) = (e for e in io.events if isinstance(e, ClausePlayed))
    assert (played.remaining_requests, played.cut_short, played.reply_id) == (9, True, 1)
    messages = [e.message for e in io.events if isinstance(e, FromClient)]
    assert [m.type for m in messages] == ["hangup", "playback", "hangup"]


def test_the_fake_io_reads_a_clients_text_as_a_call_does(settings: VoiceSettings) -> None:
    """`json.loads`, as Pipecat does, then the object path: a key the text held twice gives its
    last value, as in a call, though the text path would refuse it."""
    io = FakeSessionIO(settings)
    io.attach(FakeSession(io.setup, io.commands))

    async def call() -> FromClient:
        await io.connected()
        with pytest.raises(ValueError):  # not JSON: Pipecat drops it
            await io.client("ping")
        return await io.client('{"v": 2, "type": "stop", "v": 1}')

    assert asyncio.run(call()).message == Stop(v=1, type="stop")


def test_after_a_transport_failure_only_a_requests_report_comes(
    settings: VoiceSettings,
) -> None:
    """The failure ends the call; the report of a request that went before it is still handed,
    and nothing at all once the call's stream has ended."""
    io = FakeSessionIO(settings)
    session = FakeSession(io.setup, io.commands)
    io.attach(session)

    async def call() -> TransportFailure:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        failure = await io.transport_failure("connect")
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.caller_audio(0.02)  # not even a tap
        await io.transcribing(0, audio_s=2.0)
        await io.synthesizing(0, 0)
        await io.close()
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.transcribing(0)
        return failure

    assert asyncio.run(call()).stage == "connect" and io.ended and session.closed
    assert [type(e) for e in io.events][-3:] == [TransportFailure, Transcribing, Synthesizing]


def test_the_fake_io_hands_an_overlaps_parts_only_for_a_turn_marked_an_overlap(
    settings: VoiceSettings,
) -> None:
    """The window and the overlap name their part; the turn's own transcript reuses the
    overlap's request when it has none of its own; a part of a turn no `HearOverlap` marked is
    refused."""
    io = FakeSessionIO(settings)

    def replies(event: SessionEvent) -> list[Command]:
        opened = isinstance(event, TurnOpened) and event.turn_id == 0
        return [HearOverlap(turn_id=0, window_ms=750)] if opened else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.clock.advance(0.75)
        await io.transcribing(0, audio_s=0.75, part="window")
        await io.transcribed(0, "made-up", language="en", part="window")
        await io.clock.advance(0.5)
        await io.transcribing(0, audio_s=1.2, part="overlap")
        await io.transcribed(0, "made-up words", language="en", part="overlap")
        await io.turn_closed(0)
        await io.transcribed(0, "made-up words", language="en")  # reused: no request
        await io.turn_opened(1)
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.transcribing(1, part="window")

    asyncio.run(call())
    sent = [(e.part, e.at, e.audio_s) for e in io.events if isinstance(e, Transcribing)]
    assert sent == [("window", 100.75, 0.75), ("overlap", 101.25, 1.2)]
    heard = [(e.part, e.sent_at, e.audio_s) for e in io.events if isinstance(e, Transcribed)]
    assert heard == [("window", 100.75, 0.75), ("overlap", 101.25, 1.2), ("turn", 101.25, 1.2)]
    assert io.overlaps == {0} and io.commands.of(HearOverlap)[0].window_ms == 750


class _CallsBack:
    """`Commands` that break io.py's rule: `run` calls the session back from inside."""

    def __init__(self) -> None:
        self.session: FakeSession | None = None

    async def run(self, command: Command) -> None:
        assert self.session is not None
        await self.session.handle(Connected(at=0.0))


class _Waits:
    """`Commands` whose `run` waits until `go` is set, or `forever`."""

    def __init__(self, *, forever: bool = False) -> None:
        self.go = asyncio.Event()
        self.forever = forever
        self.ran: list[Command] = []

    async def run(self, command: Command) -> None:
        self.ran.append(command)
        if self.forever:
            await asyncio.sleep(3600)
        await self.go.wait()


def test_the_fake_session_holds_its_lock_and_fails_a_run_that_breaks_ios_rule(
    settings: VoiceSettings,
) -> None:
    """TD-068: a `run` that calls the session back fails at once, one that does not return
    fails after `run_s`, and each step waits for the one before it to release the lock."""
    io, hello = FakeSessionIO(settings), Send(message=State(state="listening"))
    calls_back = _CallsBack()
    calls_back.session = FakeSession(io.setup, calls_back)
    waits = _Waits(forever=True)
    stuck = FakeSession(io.setup, waits, run_s=0.01)
    held = _Waits()
    serial = FakeSession(io.setup, held, replies=lambda event: [hello])

    async def call() -> None:
        session = calls_back.session
        assert session is not None
        with pytest.raises(RuntimeError, match=r"called the session's handle.*TD-068"):
            await session.give(hello)
        with pytest.raises(RuntimeError, match=r"did not return within 0.01 s.*FIX: "):
            await stuck.give(hello)
        first = asyncio.create_task(serial.handle(Connected(at=1.0)))
        second = asyncio.create_task(serial.handle(Connected(at=2.0)))
        for _ in range(5):
            await asyncio.sleep(0)
        assert [event.at for event in serial.events] == [1.0]  # the second waits on the lock
        held.go.set()
        await asyncio.gather(first, second)
        await serial.aclose()

    asyncio.run(call())
    assert [event.at for event in serial.events] == [1.0, 2.0] and serial.closed
    assert held.ran == [hello, hello] and waits.ran == [hello] and RUN_S == 5.0


def test_the_slow_responder_is_held_on_the_fake_clock_and_cancelled_there() -> None:
    """Its stream and its lookup sleep on the fake clock: they finish when it has moved far
    enough, and a cancel mid-flight is recorded at the clock's time."""
    clock = FakeClock(start=0.0)
    whole, stopped = SlowResponder(clock), SlowResponder(clock, chunk_s=2.0, lookup_s=9.0)

    async def call() -> tuple[str, str]:
        text = asyncio.create_task(whole.read())
        found = asyncio.create_task(whole.lookup("a made-up query"))
        cut = [asyncio.create_task(stopped.read()), asyncio.create_task(stopped.lookup("q"))]
        await clock.advance(0.0)  # each starts, and sleeps
        await clock.advance(5.0)
        for task in cut:
            task.cancel()
        results = await asyncio.gather(*cut, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        return await text, await found

    assert asyncio.run(call()) == (" ".join(CHUNKS), "found for a made-up query")
    assert (whole.started, whole.finished, whole.cancelled) == (
        {"stream": 0.0, "lookup": 0.0},
        {"stream": 3.0, "lookup": 5.0},
        {},
    )
    assert (stopped.finished, stopped.cancelled) == ({}, {"stream": 5.0, "lookup": 5.0})
