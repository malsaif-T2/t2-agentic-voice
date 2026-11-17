"""The session's I/O (voice/session/io.py, with session_events.py and commands.py; plan 003's
step 10): the lists name every event and command once; each is frozen and keyword-only, every
event carries its time, every turn's event its turn and every clause's its reply, never a turn;
a turn's requests name their part, its whole speech's unless an overlap's names another; a
session and a Pipecat side written against the protocols talk through them alone, the call's
stream ending with the session's `aclose`; and the system clock is the performance counter, the
aware UTC time and asyncio's sleep."""

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
from t2_agentic_voice.voice.session.commands import (
    COMMANDS,
    Command,
    HangUp,
    HearOverlap,
    ListenIn,
    ReadBackWait,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, CallSetup, Commands, Session
from t2_agentic_voice.voice.session.session_events import (
    SESSION_EVENTS,
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

FRAME = AudioChunk(pcm16=b"\x00\x00" * 2400, sample_rate=24_000)  # a cached phrase's 0.1 s
EVENTS: list[SessionEvent] = [
    Connected(at=0.0),
    TurnOpened(turn_id=0, at=1.34, speech_at=1.0),
    TurnHeld(turn_id=0, at=1.9),  # the early start's signals (plan 006)
    HoldResumed(turn_id=0, at=2.1),
    TurnClosed(turn_id=0, at=2.6, speech_ended_at=2.5),
    Transcribing(turn_id=0, at=2.61, audio_s=2.1),
    Transcribed(
        turn_id=0,
        at=2.9,
        audio_s=2.1,
        sent_at=2.61,
        transcript=Transcript(text="made-up words", language="en"),
    ),
    Synthesizing(reply_id=1, clause=1, at=2.91),
    ClauseQueued(reply_id=1, clause=0, at=2.95, requested_at=None),
    ClausePlayed(reply_id=1, clause=0, at=3.05, audio_s=0.1, chunks=1),
    ClauseFailed(reply_id=1, clause=1, at=3.2, failure="timeout", retryable=True),
    CallerAudio(pcm16=b"\x00\x00" * 320, sample_rate=16_000, at=3.3),
    AgentAudio(pcm16=b"\x00\x00" * 480, sample_rate=24_000, at=3.3),
    FromClient(message=parse_client_message({"v": 1, "type": "hangup"}), at=3.4),
    TransportFailure(stage="media", at=40.0),
    Ending(reason="caller_left", at=41.0),
]
COMMAND_EXAMPLES: list[Command] = [
    ListenIn(language="en"),
    HearOverlap(turn_id=0, window_ms=750),
    Speak(reply_id=1, clause=0, turn_id=0, text="I heard:", language="en", audio=FRAME),
    StopSpeaking(reply_id=1),
    Send(message=State(state="listening")),
    HangUp(reason="hangup"),
    ReadBackWait(waiting=True),
]
TURNS = {TurnOpened, TurnHeld, HoldResumed, TurnClosed, Transcribing, Transcribed}
CLAUSES = {Synthesizing, ClauseQueued, ClausePlayed, ClauseFailed}


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


def test_every_event_carries_its_time_a_turns_its_turn_and_a_clauses_its_reply() -> None:
    """A clause is keyed on its reply, never on a turn, so the greeting (reply 0) and a turn's
    echo never share a key; `Speak` names the turn a reply answers, and a command carries no
    time. The greeting, a fixed phrase, names no turn and plays its cached audio."""
    for event in EVENTS:
        names = {field.name for field in dataclasses.fields(event)}
        assert "at" in names and isinstance(event.at, float), event
        assert ("turn_id" in names) == (type(event) in TURNS), event
        assert ({"reply_id", "clause"} <= names) == (type(event) in CLAUSES), event
    for command in COMMAND_EXAMPLES:
        names = {field.name for field in dataclasses.fields(command)}
        assert "at" not in names
        assert ("reply_id" in names) == isinstance(command, Speak | StopSpeaking)
    greeting = Speak(
        reply_id=0, clause=0, turn_id=None, text="Hello there.", language="en", audio=FRAME
    )
    assert (greeting.turn_id, greeting.audio) == (None, FRAME)


def test_a_turns_requests_name_their_part_the_whole_turns_unless_another_is_named() -> None:
    """A turn's request and transcript are its `turn` part unless the bridge names another, so a
    call with no overlap reads as it did; an overlap's `window` and `overlap` name themselves."""
    request, answer = EVENTS[5], EVENTS[6]
    assert isinstance(request, Transcribing) and isinstance(answer, Transcribed)
    assert (request.part, answer.part) == ("turn", "turn")
    assert get_args(TranscriptPart) == ("window", "overlap", "turn", "held")
    window = Transcribing(turn_id=2, at=5.0, audio_s=0.75, part="window")
    heard = Transcribed(
        turn_id=2, at=5.3, audio_s=0.75, sent_at=5.0, transcript=None, part="overlap"
    )
    assert (window.part, heard.part) == ("window", "overlap")


class _Phrases:
    """The one phrase declared (a `PhraseAudio`): the English frame."""

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
    """A session written against the protocols alone: it names the call's language, says the
    frame from the cache once a turn's transcript is in, then the heard words, as the next
    reply (the greeting left out), hangs up when the call ends from outside, and counts the
    speech-to-text requests that went until its stream ends."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        self.setup, self.commands = setup, commands
        self.replies = 0
        self.requests: list[float] = []
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True

    async def handle(self, event: SessionEvent) -> None:
        language = self.setup.language
        if isinstance(event, Connected):
            await self.commands.run(ListenIn(language=language.primary))
        elif isinstance(event, Transcribing):
            self.requests.append(event.audio_s)
        elif isinstance(event, Transcribed) and event.transcript is not None:
            self.replies += 1
            reply, turn, tag = self.replies, event.turn_id, language.tag
            frame = self.setup.phrases.audio(language.echo_frame, language=tag)
            first = Speak(
                reply_id=reply, clause=0, turn_id=turn, text=language.echo_frame, language=tag
            )
            await self.commands.run(dataclasses.replace(first, audio=frame))
            heard = event.transcript.text
            await self.commands.run(dataclasses.replace(first, clause=1, text=heard))
        elif isinstance(event, Ending):
            await self.commands.run(HangUp(reason=event.reason))


def test_a_session_and_a_pipecat_side_talk_through_the_protocols_alone(
    settings: VoiceSettings,
) -> None:
    emitted: list[Event] = []
    english = Language.english(greeting="Hello there.")
    setup = CallSetup(
        call_id="call-1",
        caller=Caller(subject="made-up"),
        consent=Consent(version=None, record_audio=False),
        agent=VoiceAgent(name="echo", languages=[english]),
        language=english,
        settings=settings,
        phrases=_Phrases(),
        max_chars=lambda language: 200,
        tracing=Tracing(),
        emit=emitted.append,
    )
    side = _PipecatSide()
    echo = _Echo(setup, side)
    session: Session = echo  # mypy checks both protocols' shapes
    commands: Commands = side

    async def call() -> None:
        for event in EVENTS:
            await session.handle(event)
        await session.aclose()

    asyncio.run(call())
    assert commands is side and setup.clock is SYSTEM_CLOCK and emitted == []
    assert [type(command) for command in side.commands] == [ListenIn, Speak, Speak, HangUp]
    assert side.commands[-1] == HangUp(reason="caller_left")
    speaks = [c for c in side.commands if isinstance(c, Speak)]
    assert [(c.reply_id, c.clause, c.turn_id) for c in speaks] == [(1, 0, 0), (1, 1, 0)]
    assert [c.audio for c in speaks] == [FRAME, None]  # the frame from the cache, no request
    assert (echo.requests, echo.closed) == ([2.1], True)  # counted from its Transcribing
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
