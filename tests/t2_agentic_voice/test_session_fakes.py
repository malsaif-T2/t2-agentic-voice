"""The fakes of the session's I/O (tests/t2_agentic_voice/session_fakes.py) implement their
protocols of voice/session/io.py, so the session (Track D) and the Pipecat side (Track E) build
against the real interfaces: each is assigned to its protocol, which mypy checks, and does what
its docstring says."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from t2_agentic_voice import InvalidRequestError
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.events import CallStarted
from t2_agentic_voice.voice.protocol import Hangup, State
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.io import (
    COMMANDS,
    SESSION_EVENTS,
    CallSetup,
    ClausePlayed,
    Command,
    Commands,
    FromClient,
    HangUp,
    ListenIn,
    Phrases,
    Send,
    Session,
    SessionEvent,
    Speak,
    StopSpeaking,
    Transcribed,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.session_fakes import (
    AGENT,
    CALLER,
    PLAIN_CONSENT,
    FakeCommands,
    FakePhrases,
    FakeSession,
    FakeSessionIO,
)

# Every command of io.py, one of each kind.
ONE_OF_EACH: list[Command] = [
    ListenIn(language="en"),
    Speak(turn_id=0, clause=0, text="a clause for the test", language="en"),
    StopSpeaking(turn_id=0),
    Send(message=State(state="listening")),
    HangUp(reason="hangup"),
]


def test_one_of_each_command_is_every_command() -> None:
    assert [type(c) for c in ONE_OF_EACH] == list(COMMANDS)


def test_the_fake_phrases_give_only_the_phrases_declared() -> None:
    fake = FakePhrases.of(AGENT)
    phrases: Phrases = fake
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
    assert len(fake.declared) == 4


def test_the_fake_commands_keep_each_command() -> None:
    fake = FakeCommands()
    commands: Commands = fake

    async def run_all() -> None:
        for command in ONE_OF_EACH:
            await commands.run(command)

    asyncio.run(run_all())
    assert fake.commands == ONE_OF_EACH
    assert fake.of(StopSpeaking) == [StopSpeaking(turn_id=0)]
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
        await session.give(HangUp(reason="hangup"))

    asyncio.run(drive())
    assert session.events == io.events and session.setup is io.setup and build is CallSession
    assert io.commands.commands == [hello, HangUp(reason="hangup")]


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
        await io.clock.advance(0.5)
        await io.transcribed(0, "words of the test", language="en", audio_s=1.4)
        await io.turn_opened(1)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await io.transcribed(1, None)
        await io.clause_queued(0, 0)
        await io.agent_audio(0.04)
        await io.clause_played(0, 0, audio_s=0.6, chunks=3, remaining=(9, 900), cut_short=True)
        await io.clause_failed(0, 1, failure="rejected")
        await io.client({"v": 1, "type": "hangup"})
        await io.client('{"v": 1, "type": "playback", "turn_id": 0, "clause": 0, "event": "ended"}')
        await io.client(Hangup(v=1, type="hangup"))
        with pytest.raises(InvalidRequestError):
            await io.client({"v": 1, "type": "hangup", "consent": True})
        await io.transport_failure("connect")
        await io.ending()

    asyncio.run(call())
    assert session.events == io.events
    assert {type(event) for event in io.events} == set(SESSION_EVENTS)
    opened, _, closed, heard, other, failed, nothing = io.events[1:8]
    assert isinstance(opened, TurnOpened) and (opened.at, opened.speech_at) == (100.0, 99.5)
    assert isinstance(closed, TurnClosed) and (closed.at, closed.speech_ended_at) == (101.5, 101.0)
    assert isinstance(heard, Transcribed) and heard.transcript is not None
    assert (heard.at, heard.sent_at, heard.audio_s) == (102.0, 101.5, 1.4)
    assert (heard.transcript.text, heard.transcript.billed_seconds) == ("words of the test", 10.0)
    assert isinstance(other, TurnOpened) and other.speech_at == other.at == 102.0
    assert isinstance(failed, Transcribed) and (failed.failure, failed.sent_at) == (
        "timeout",
        102.0,
    )
    assert isinstance(nothing, Transcribed) and (nothing.transcript, nothing.sent_at) == (
        None,
        None,
    )
    played = io.events[10]
    assert isinstance(played, ClausePlayed) and (played.remaining_requests, played.cut_short) == (
        9,
        True,
    )
    messages = [e.message for e in io.events if isinstance(e, FromClient)]
    assert [m.type for m in messages] == ["hangup", "playback", "hangup"]
