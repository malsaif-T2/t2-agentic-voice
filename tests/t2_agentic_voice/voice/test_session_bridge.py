"""The session bridge (voice/session_bridge.py): the call's stream of session events, the client's
messages, and the session's commands carried out, against the fakes."""

from __future__ import annotations

import asyncio
import logging

import pytest
from t2_agentic_voice.voice import session_bridge as bridge_module
from t2_agentic_voice.voice.protocol import Duck, Hangup, State, wire
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
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.session.session_events import (
    ClausePlayed,
    ClauseQueued,
    Connected,
    Ending,
    FromClient,
    SessionEvent,
    Synthesizing,
    Transcribing,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import (
    EventStream,
    SessionBridge,
    SessionCommands,
    SpeakFrame,
    clause_of,
    context_id,
)

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.voice.kit import Recorder, Tail, run_pipeline, until


def _played(reply: int, clause: int = 0, at: float = 1.0) -> ClausePlayed:
    return ClausePlayed(reply_id=reply, clause=clause, at=at, audio_s=0.5, chunks=1)


def test_a_clause_is_named_in_its_context_and_read_back() -> None:
    assert clause_of(context_id((3, 7))) == (3, 7)
    assert clause_of("some-other-context") is None and clause_of(None) is None


def test_the_stream_hands_events_in_order_and_holds_what_cannot_come() -> None:
    """Events reach the session in the order handed; a stop drops every clause asked for so far,
    a request's report waiting for a busy session included (TD-055), and later events of
    them; after the end only a request's report is handed; after the close, nothing."""

    async def run() -> Recorder:
        events, session = EventStream(FakeClock(), record=True), Recorder()
        session.block = asyncio.Event()
        events.start(session)
        events.hand(Connected(at=1.0))
        events.asked |= {(0, 0), (1, 0)}
        events.hand(Synthesizing(reply_id=1, clause=0, at=1.1))  # waits: the session is busy
        events.hand(ClauseQueued(reply_id=0, clause=0, at=1.2, requested_at=None))
        events.stop_speaking()
        events.hand(_played(0))  # of a dropped clause: never handed
        events.hand(_played(2))  # asked for after the stop: handed
        events.hand(Ending(reason="caller_left", at=2.0))
        events.hand(TurnOpened(turn_id=0, at=2.1, speech_at=2.0))  # after the end: held
        events.hand(Transcribing(turn_id=0, at=2.2, audio_s=1.0))  # a report: handed
        session.block.set()
        await events.close()
        events.hand(Transcribing(turn_id=1, at=3.0, audio_s=1.0))  # after the close: nothing
        assert events.handed == session.events
        return session

    session = asyncio.run(run())
    assert [type(e) for e in session.events] == [Connected, ClausePlayed, Ending, Transcribing]
    assert session.of(ClausePlayed)[0].reply_id == 2 and session.closed


def test_the_session_hanging_up_lets_only_a_requests_report_through() -> None:
    async def run() -> Recorder:
        events, session = EventStream(FakeClock()), Recorder()
        session.block = asyncio.Event()
        events.start(session)
        events.hand(_played(0))
        events.hand(Transcribing(turn_id=0, at=1.0, audio_s=1.0))
        events.end()
        events.hand(_played(1))
        session.block.set()
        await events.close()
        return session

    assert [type(e) for e in asyncio.run(run()).events] == [Transcribing]


def test_a_session_that_raises_or_hangs_never_holds_the_stream(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """io.py says a session never raises; if one does, the stream logs the event's kind and goes
    on; one that hangs is given `CLOSE_WAIT_S` at the close, and one whose `aclose` fails is
    logged, so a call always ends."""
    monkeypatch.setattr(bridge_module, "CLOSE_WAIT_S", 0.05)

    class Faulty(Recorder):
        async def handle(self, event: SessionEvent) -> None:
            if isinstance(event, Connected):
                raise RuntimeError("the session's own text")
            await super().handle(event)

        async def aclose(self) -> None:
            raise RuntimeError("the session's own text")

    async def run(session: Recorder) -> None:
        events = EventStream(SYSTEM_CLOCK)
        events.start(session)
        events.hand(Connected(at=1.0))
        events.hand(_played(0))
        await asyncio.sleep(0.05)
        await events.close()

    faulty = Faulty()
    asyncio.run(run(faulty))
    assert [type(e) for e in faulty.events] == [ClausePlayed]
    stuck = Recorder()
    stuck.block = asyncio.Event()  # never set
    asyncio.run(run(stuck))
    lines = [r.getMessage() for r in caplog.records]
    assert "session_event_failed" in lines and "session_close_failed" in lines
    assert "call_events_close_timeout" in lines and "own text" not in caplog.text


def test_closing_a_stream_never_started_ends_at_once() -> None:
    events = EventStream(SYSTEM_CLOCK)
    asyncio.run(events.close())
    assert events.closed and events.ended


def test_the_bridge_hands_the_client_messages_and_passes_every_other_frame(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A client message the transport parsed reaches the session as `FromClient`; one that is
    not `t2v/1`'s is dropped with a line naming only the kind of problem; an upstream copy is
    taken nowhere; other frames pass on downstream."""
    from pipecat.frames.frames import InputTransportMessageFrame, UserSpeakingFrame
    from pipecat.processors.frame_processor import FrameDirection

    caplog.set_level(logging.INFO)
    events, session, tail = EventStream(SYSTEM_CLOCK), Recorder(), Tail()
    bridge = SessionBridge(events)

    async def feed(worker: object) -> None:
        events.start(session)
        hangup = {"v": 1, "type": "hangup"}
        await bridge.queue_frame(InputTransportMessageFrame(message=hangup))
        await bridge.queue_frame(InputTransportMessageFrame(message={"v": 1, "type": "secret"}))
        await bridge.queue_frame(
            InputTransportMessageFrame(message=hangup), FrameDirection.UPSTREAM
        )
        await bridge.queue_frame(UserSpeakingFrame())
        await until(lambda: bool(session.events) and bool(tail.frames))
        await events.close()

    asyncio.run(run_pipeline([bridge, tail], feed))
    assert [e.message for e in session.of(FromClient)] == [Hangup(v=1, type="hangup")]
    assert len(tail.of(UserSpeakingFrame)) == 1
    assert tail.of(InputTransportMessageFrame) == []
    assert "client_message_dropped" in caplog.text and "secret" not in caplog.text


def test_the_commands_are_carried_out_in_order_and_never_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`ListenIn` names the language, `HearOverlap` marks the bridge's turn an overlap, `Speak`
    sends its clause downstream and counts it asked for, `StopSpeaking` drops what was asked and
    broadcasts the interruption, `Send` hands the message on, `HangUp` ends the stream and the
    call; after the end a mark, a `Speak` or a stop does nothing, and a command that fails is
    logged, not raised; each is kept with its time."""
    from pipecat.frames.frames import InterruptionFrame

    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    clock = FakeClock()
    events, tail = EventStream(clock), Tail()
    bridge = SessionBridge(events)
    heard: list[str | None] = []
    marked: list[tuple[int, int]] = []
    sent: list[object] = []
    ended: list[str] = []

    async def send(message: object) -> None:
        if message == wire(State(state="thinking")):
            raise RuntimeError("the transport's own text")
        sent.append(message)

    commands = SessionCommands(
        bridge,
        events,
        listen=heard.append,
        hear=lambda turn_id, window_ms: marked.append((turn_id, window_ms)),
        send=send,
        hang_up=ended.append,
        record=True,
    )
    speak = Speak(reply_id=0, clause=0, turn_id=None, text="Hello", language="en")

    async def feed(worker: object) -> None:
        await commands.run(ListenIn(language="en"))
        await commands.run(HearOverlap(turn_id=2, window_ms=750))
        await commands.run(speak)
        await until(lambda: bool(tail.of(SpeakFrame)))
        await commands.run(StopSpeaking(reply_id=0))
        await commands.run(Send(message=State(state="listening")))
        await commands.run(Send(message=State(state="thinking")))
        await commands.run(HangUp(reason="hangup"))
        await commands.run(HearOverlap(turn_id=3, window_ms=750))
        await commands.run(speak)
        await commands.run(StopSpeaking(reply_id=0))
        await until(lambda: bool(tail.of(InterruptionFrame)))

    asyncio.run(run_pipeline([bridge, tail], feed))
    assert heard == ["en"] and sent == [wire(State(state="listening"))] and ended == ["hangup"]
    assert marked == [(2, 750)]
    assert events.asked == events.dropped == {(0, 0)} and events.ended
    assert [f.speak for f in tail.of(SpeakFrame)] == [speak]
    assert commands.given is not None and len(commands.given) == 10
    assert commands.given[0] == (clock.now(), ListenIn(language="en"))
    lines = [r.getMessage() for r in caplog.records]
    assert lines.count("command_after_end") == 3 and "command_failed" in lines
    assert "own text" not in caplog.text


def test_every_command_of_the_session_has_its_case(caplog: pytest.LogCaptureFixture) -> None:
    """Each type of `COMMANDS`, given before the call's end, is carried out by a case of its
    own: none falls to the line kept for a command after the end. A new command type fails
    here until it has a sample below, and a case."""
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    events = EventStream(FakeClock())
    bridge = SessionBridge(events)
    done: list[str] = []
    commands = SessionCommands(
        bridge,
        events,
        listen=lambda language: done.append("ListenIn"),
        hear=lambda turn_id, window_ms: done.append("HearOverlap"),
        send=lambda message: _noted(done, "Send"),
        hang_up=lambda reason: done.append("HangUp"),
    )
    samples: list[Command] = [
        ListenIn(language="en"),
        HearOverlap(turn_id=0, window_ms=750),
        Speak(reply_id=0, clause=0, turn_id=None, text="Hello", language="en"),
        StopSpeaking(reply_id=0),
        Send(message=Duck(level=0.25)),
        HangUp(reason="hangup"),
    ]
    assert {type(sample) for sample in samples} == set(COMMANDS)

    async def feed(worker: object) -> None:
        for sample in samples:
            await commands.run(sample)

    asyncio.run(run_pipeline([bridge, Tail()], feed))
    assert done == ["ListenIn", "HearOverlap", "Send", "HangUp"]
    assert events.asked == events.dropped == {(0, 0)}
    lines = [r.getMessage() for r in caplog.records]
    assert "command_after_end" not in lines and "command_failed" not in lines


async def _noted(done: list[str], name: str) -> None:
    done.append(name)
