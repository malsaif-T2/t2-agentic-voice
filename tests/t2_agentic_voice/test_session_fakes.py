"""The fakes of the session's I/O (tests/t2_agentic_voice/session_fakes.py) implement their
protocols of voice/session/io.py, so the session (Track D) and the Pipecat side (Track E) build
against the real interfaces: each is assigned to its protocol, which mypy checks, and does what
its docstring says. Two scenes show the contracts the session builds on: the greeting, with a
turn that opens while it plays, every key apart; and a call that ends with a turn still open."""

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
from t2_agentic_voice.voice.protocol import Caption, Hangup, State
from t2_agentic_voice.voice.session.call import CallSession
from t2_agentic_voice.voice.session.commands import (
    COMMANDS,
    Command,
    HangUp,
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
    Ending,
    FromClient,
    SessionEvent,
    Transcribed,
    TransportFailure,
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

# A playback report as the channel carries it.
PLAYED = '{"v": 1, "type": "playback", "reply_id": 1, "clause": 0, "event": "ended"}'
# Every command of commands.py, one of each kind.
ONE_OF_EACH: list[Command] = [
    ListenIn(language="en"),
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
        await session.give(HangUp(reason="hangup"))
        with pytest.raises(RuntimeError, match="FIX: "):  # no event follows the HangUp
            await io.turn_closed(0)

    asyncio.run(drive())
    assert session.events == io.events and session.setup is io.setup and build is CallSession
    assert io.commands.commands == [hello, HangUp(reason="hangup")] and io.ended


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
        await io.clock.advance(0.5)
        await io.transcribed(0, "words of the test", language="en", audio_s=1.4)
        await io.turn_opened(1)
        await io.transcribed(1, None, failure="timeout", retryable=True)
        await io.transcribed(1, None)
        await io.clause_queued(1, 0)
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
    assert (played.reply_id, played.clause) == (1, 0)
    messages = [e.message for e in io.events if isinstance(e, FromClient)]
    assert [m.type for m in messages] == ["hangup", "playback", "hangup"]


def test_a_transport_failure_is_the_calls_last_event(settings: VoiceSettings) -> None:
    io = FakeSessionIO(settings)
    io.attach(FakeSession(io.setup, io.commands))

    async def call() -> TransportFailure:
        await io.connected()
        failure = await io.transport_failure("connect")
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.caller_audio(0.02)  # not even a tap
        return failure

    assert asyncio.run(call()).stage == "connect" and io.ended


def test_the_greeting_and_a_turn_that_opens_while_it_plays_never_share_a_key(
    settings: VoiceSettings,
) -> None:
    """The greeting is reply 0, naming no turn. The caller's turn 0 opens while it plays, so
    the drop rule leaves it unanswered (the session's part, Track D's test); turn 1 opens after
    the greeting, and its echo is reply 1, naming turn 1. A scripted session plays the
    greeting's commands here, as `CallSession` will: every key of a reply's clause, and every
    caption's, is its own."""
    io = FakeSessionIO(settings)
    language = io.setup.language
    greeting = Speak(
        reply_id=0,
        clause=0,
        turn_id=None,
        text=language.greeting,
        language=language.tag,
        audio=io.phrases.audio(language.greeting, language=language.tag),
    )
    frame = Speak(reply_id=1, clause=0, turn_id=1, text=language.echo_frame, language="en")
    heard = Speak(reply_id=1, clause=1, turn_id=1, text="words of the test", language="en")

    def caption(speak: Speak) -> Send:
        return Send(
            message=Caption(
                speaker="agent",
                text=speak.text,
                final=True,
                turn_id=speak.turn_id,
                reply_id=speak.reply_id,
                clause=speak.clause,
            )
        )

    def replies(event: SessionEvent) -> list[Command]:
        if isinstance(event, TurnOpened) and event.turn_id == 0:
            return []  # opened during the greeting: dropped
        if isinstance(event, ClauseQueued):
            return [caption(greeting if event.reply_id == 0 else frame)]
        if isinstance(event, Transcribed) and event.turn_id == 1:
            return [frame, heard]
        if isinstance(event, Ending):
            return [HangUp(reason=event.reason)]
        return [greeting] if isinstance(event, Connected) else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        await io.clause_queued(0, 0)
        await io.clock.advance(0.2)
        await io.turn_opened(0)  # its speech began while the greeting played
        await io.clock.advance(0.3)
        await io.clause_played(0, 0, audio_s=0.5)
        await io.turn_closed(0)
        await io.transcribed(0, "the agent's own greeting, leaked")
        await io.clock.advance(1.0)
        await io.turn_opened(1)
        await io.turn_closed(1)
        await io.transcribed(1, "words of the test", language="en")
        await io.clause_queued(1, 0)
        await io.ending()

    asyncio.run(call())
    speaks = io.commands.of(Speak)
    assert speaks == [greeting, frame, heard]
    assert len({(s.reply_id, s.clause) for s in speaks}) == len(speaks)
    assert [s.turn_id for s in speaks] == [None, 1, 1]
    played = [(e.reply_id, e.clause) for e in io.events if isinstance(e, ClauseQueued)]
    captions = [m for m in io.commands.sent if isinstance(m, Caption)]
    assert played == [(0, 0), (1, 0)] and [(c.reply_id, c.clause) for c in captions] == played
    opened = [e for e in io.events if isinstance(e, TurnOpened)]
    greeted = next(e.at for e in io.events if isinstance(e, ClausePlayed))
    assert opened[0].speech_at < greeted < opened[1].speech_at  # turn 0's began in the greeting
    assert io.commands.commands[-1] == HangUp(reason="caller_left")


def test_a_call_that_ends_with_a_turn_open_hands_none_of_the_turns_events(
    settings: VoiceSettings,
) -> None:
    """The caller leaves mid-turn: the `Ending` is the call's last event, so no `TurnClosed` or
    `Transcribed` of the turn follows, and the session hangs up (Track D keeps the turn in the
    report as unfinished)."""
    io = FakeSessionIO(settings)

    def replies(event: SessionEvent) -> list[Command]:
        return [HangUp(reason=event.reason)] if isinstance(event, Ending) else []

    io.attach(FakeSession(io.setup, io.commands, replies=replies))

    async def call() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.ending()
        for late in (io.turn_closed(0), io.transcribed(0, "words of the test")):
            with pytest.raises(RuntimeError, match="FIX: "):
                await late

    asyncio.run(call())
    assert [type(e) for e in io.events][-2:] == [TurnOpened, Ending]
    assert io.commands.commands == [HangUp(reason="caller_left")]
