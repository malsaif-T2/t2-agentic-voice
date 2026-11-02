"""The session's I/O (voice/session/io.py, plan 003's step 10): the lists name every event and
command once; each is frozen and keyword-only, every event carries its time and every turn's
event its turn; a session and a Pipecat side written against the protocols talk through them
alone; and the system clock is the performance counter, the aware UTC time and asyncio's
sleep."""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import get_args

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Event
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import State, parse_client_message
from t2_agentic_voice.voice.session.io import (
    COMMANDS,
    SESSION_EVENTS,
    SYSTEM_CLOCK,
    AgentAudio,
    CallerAudio,
    CallSetup,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Command,
    Commands,
    Connected,
    Ending,
    FromClient,
    HangUp,
    ListenIn,
    Send,
    Session,
    SessionEvent,
    Speak,
    StopSpeaking,
    Transcribed,
    TransportFailure,
    TurnClosed,
    TurnOpened,
)

FRAME = AudioChunk(pcm16=b"\x00\x00" * 2400, sample_rate=24_000)  # a cached phrase's 0.1 s
EVENTS: list[SessionEvent] = [
    Connected(at=0.0),
    TurnOpened(turn_id=0, at=1.34, speech_at=1.0),
    TurnClosed(turn_id=0, at=2.6, speech_ended_at=2.5),
    Transcribed(
        turn_id=0,
        at=2.9,
        audio_s=2.1,
        sent_at=2.61,
        transcript=Transcript(text="made-up words", language="en"),
    ),
    ClauseQueued(turn_id=0, clause=0, at=2.95, requested_at=None),
    ClausePlayed(turn_id=0, clause=0, at=3.05, audio_s=0.1, chunks=1),
    ClauseFailed(turn_id=0, clause=1, at=3.2, failure="timeout", retryable=True),
    CallerAudio(pcm16=b"\x00\x00" * 320, sample_rate=16_000, at=3.3),
    AgentAudio(pcm16=b"\x00\x00" * 480, sample_rate=24_000, at=3.3),
    FromClient(message=parse_client_message({"v": 1, "type": "hangup"}), at=3.4),
    TransportFailure(stage="media", at=40.0),
    Ending(reason="caller_left", at=41.0),
]
COMMAND_EXAMPLES: list[Command] = [
    ListenIn(language="en"),
    Speak(turn_id=0, clause=0, text="I heard:", language="en", audio=FRAME),
    StopSpeaking(turn_id=0),
    Send(message=State(state="listening")),
    HangUp(reason="hangup"),
]
TURNS = {TurnOpened, TurnClosed, Transcribed, ClauseQueued, ClausePlayed, ClauseFailed}


def test_each_event_and_command_is_listed_once_in_the_unions_order() -> None:
    assert get_args(SessionEvent) == SESSION_EVENTS
    assert get_args(Command) == COMMANDS
    assert [type(event) for event in EVENTS] == list(SESSION_EVENTS)
    assert [type(command) for command in COMMAND_EXAMPLES] == list(COMMANDS)


@pytest.mark.parametrize("example", [*EVENTS, *COMMAND_EXAMPLES], ids=lambda e: type(e).__name__)
def test_each_is_frozen_and_keyword_only(example: SessionEvent | Command) -> None:
    fields = dataclasses.fields(example)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(example, fields[0].name, None)
    values = [getattr(example, field.name) for field in fields]
    with pytest.raises(TypeError, match="positional"):
        kind: Callable[..., object] = type(example)
        kind(*values)


def test_every_event_carries_its_time_and_every_turns_event_its_turn() -> None:
    for event in EVENTS:
        names = {field.name for field in dataclasses.fields(event)}
        assert "at" in names and isinstance(event.at, float), event
        assert ("turn_id" in names) == (type(event) in TURNS), event
    for command in COMMAND_EXAMPLES:
        assert "at" not in {field.name for field in dataclasses.fields(command)}


class _Phrases:
    """The one phrase declared: the English frame."""

    def audio(self, text: str, *, language: str) -> AudioChunk:
        if (text, language) != ("I heard:", "en"):
            raise LookupError("not declared")
        return FRAME


class _PipecatSide:
    """Keeps every command the session gives."""

    def __init__(self) -> None:
        self.commands: list[Command] = []

    async def run(self, command: Command) -> None:
        self.commands.append(command)


class _Echo:
    """A session written against the protocols alone: it names its language, says the frame
    from the cache once a turn's transcript is in, then the heard words, and hangs up when the
    call ends from outside."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        self.setup, self.commands = setup, commands

    async def handle(self, event: SessionEvent) -> None:
        if isinstance(event, Connected):
            await self.commands.run(ListenIn(language="en"))
        elif isinstance(event, Transcribed) and event.transcript is not None:
            turn, heard = event.turn_id, event.transcript.text
            frame = self.setup.phrases.audio("I heard:", language="en")
            await self.commands.run(
                Speak(turn_id=turn, clause=0, text="I heard:", language="en", audio=frame)
            )
            await self.commands.run(Speak(turn_id=turn, clause=1, text=heard, language="en"))
        elif isinstance(event, Ending):
            await self.commands.run(HangUp(reason=event.reason))


def test_a_session_and_a_pipecat_side_talk_through_the_protocols_alone(
    settings: VoiceSettings,
) -> None:
    emitted: list[Event] = []
    setup = CallSetup(
        call_id="call-1",
        caller=Caller(subject="made-up"),
        consent=Consent(version=None, record_audio=False),
        agent=VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")]),
        settings=settings,
        phrases=_Phrases(),
        max_chars=lambda language: 200,
        tracing=Tracing(),
        emit=emitted.append,
    )
    side = _PipecatSide()
    session: Session = _Echo(setup, side)  # mypy checks both protocols' shapes
    commands: Commands = side

    async def call() -> None:
        for event in EVENTS:
            await session.handle(event)

    asyncio.run(call())
    assert commands is side and setup.clock is SYSTEM_CLOCK and emitted == []
    assert [type(command) for command in side.commands] == [ListenIn, Speak, Speak, HangUp]
    assert side.commands[-1] == HangUp(reason="caller_left")
    with pytest.raises(LookupError):
        setup.phrases.audio("made-up words", language="en")


def test_the_system_clock_is_the_performance_counter_utc_and_asyncios_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = time.perf_counter()
    now = SYSTEM_CLOCK.now()
    assert before <= now <= time.perf_counter()
    wall = SYSTEM_CLOCK.wall()
    assert wall.tzinfo is UTC and abs((datetime.now(UTC) - wall).total_seconds()) < 5
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)  # the module io.py sleeps through
    asyncio.run(SYSTEM_CLOCK.sleep(0.3))
    assert slept == [0.3]
