"""The stop and the end (voice/session/call.py; io.py's stop path and end): a `stop` drops every
reply asked for so far in one `StopSpeaking` naming the newest, each counted as done at once, and
the session listens again; a stop that drops the `ended` notice hangs up at once; whatever ends
the call (an `Ending`, a `TransportFailure`, a `hangup` message, `limits.max_call_s`,
`limits.idle_s`), its `HangUp` comes at once (for a limit, once its notice has played), a turn
still open or with its transcript to come stays unfinished, and an echo it cut ends with what
played."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    EndReason,
    Interrupted,
    TransportFailed,
)
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.voice.protocol import Ended, Notice, State
from t2_agentic_voice.voice.session.commands import HangUp, StopSpeaking
from t2_agentic_voice.voice.session.session_events import Connected, TurnOpened

from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    drop,
    emitted,
    greeted,
    play,
    report,
    sent,
    speaks,
    turn,
)


def test_a_stop_drops_every_reply_asked_for_and_the_session_listens_again(
    settings: VoiceSettings,
) -> None:
    """Echo 1's heard words fail while its frame plays, so the `error` notice is queued as reply
    2 behind it; a `stop` gives one `StopSpeaking` naming reply 2, both replies end at once
    (stopped, with what played), no event of either is awaited, and turn 1 is said back as
    reply 3. A stop with nothing asked for gives no command."""
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await io.client({"v": 1, "type": "stop"})  # nothing to stop
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.synthesizing(1, 1)
        await io.clause_failed(1, 1)
        await io.client('{"v": 1, "type": "stop"}')
        await io.clock.advance(1.0)
        await turn(io, 1, HEARD)
        await play(io, 3)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=2)]
    assert io.dropped >= {(1, 0), (1, 1), (2, 0)}
    assert {s.reply_id for s in speaks(io)} == {0, 1, 2, 3}
    stopped = [e.turn_id for e in emitted(io, Interrupted)]
    assert stopped == [0, None] and {e.kind for e in emitted(io, Interrupted)} == {"stop"}
    ended = [(e.turn_id, e.played_fraction) for e in emitted(io, AgentSpeechEnded)]
    assert ended[1:3] == [(0, 0.0), (None, 0.0)] and ended[3] == (1, 1.0)
    first, second = report(io).turns
    assert first.stopped and not second.stopped
    states = [m.state for m in sent(io, State)]
    assert states[states.index("speaking", 2) + 1] == "listening"


def test_a_stop_that_drops_the_ended_notice_hangs_up_at_once(settings: VoiceSettings) -> None:
    """Under `drop`, plan 003's stop path, whose stop sends no caption again marked cut (as
    `two_step`'s does: test_overlap_order.py): at `limits.max_call_s` the `ended` notice is
    queued as reply 2 behind echo 1, still playing. A stop drops both, so the notice never
    plays: the session hangs up at once."""
    limits = LimitSettings(max_call_s=30.0, idle_s=60.0)
    short = drop(settings).model_copy(update={"limits": limits})
    io, _ = call(short)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.clock.advance(limits.max_call_s)  # the limit, while echo 1 plays
        assert [n.kind for n in sent(io, Notice)] == ["ended"] and speaks(io, 2)
        await io.client({"v": 1, "type": "stop"})
        await io.close()

    asyncio.run(drive())
    assert io.commands.commands[-3:] == [
        StopSpeaking(reply_id=2),
        Send_ended("max_call"),
        HangUp(reason="max_call"),
    ]
    assert report(io).ended_by == "max_call"


def Send_ended(reason: EndReason) -> object:  # noqa: N802 - reads as the command it builds
    from t2_agentic_voice.voice.session.commands import Send

    return Send(message=Ended(reason=reason))


ENDERS: list[tuple[str, EndReason]] = [
    ("ending", "caller_left"),
    ("server", "server"),
    ("transport", "transport"),
    ("hangup", "hangup"),
    ("max_call", "max_call"),
]


@pytest.mark.parametrize(("ender", "reason"), ENDERS, ids=[ender for ender, _ in ENDERS])
@pytest.mark.parametrize("closed", [False, True], ids=["open", "transcript-to-come"])
def test_whatever_ends_the_call_a_turn_not_yet_heard_stays_unfinished(
    settings: VoiceSettings, ender: str, reason: EndReason, closed: bool
) -> None:
    """A turn still open, or closed with its transcript still to come, when the call ends: the
    `HangUp` comes at once (for the limit, once its notice has played), no `Transcribed` of the
    turn can follow, and the report keeps it as unfinished."""
    limits = LimitSettings(max_call_s=20.0, idle_s=60.0)
    io, _ = call(settings.model_copy(update={"limits": limits}))

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        if closed:
            await io.turn_closed(0)
            await io.transcribing(0, audio_s=2.0)
        if ender == "ending":
            await io.ending()
        elif ender == "server":
            await io.ending("server")
        elif ender == "transport":
            await io.transport_failure("media")
        elif ender == "hangup":
            await io.client({"v": 1, "type": "hangup"})
        else:
            await io.clock.advance(limits.max_call_s)
            assert not io.ended  # the notice plays first
            await play(io, 1)
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.transcribed(0, HEARD)
        await io.close()

    asyncio.run(drive())
    assert io.commands.commands[-1] == HangUp(reason=reason)
    told = [] if ender in ("ending", "transport") else [Ended(reason=reason)]
    assert sent(io, Ended) == told
    (record,) = report(io).turns
    assert record.unfinished and report(io).ended_by == reason
    assert len(emitted(io, TransportFailed)) == (ender == "transport")


def test_an_echo_the_end_cut_ends_with_what_played(settings: VoiceSettings) -> None:
    """The caller leaves while the echo's heard words are queued: they get no event, and the
    reply ends as cut, its `AgentSpeechEnded` saying how much played."""
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.clause_played(1, 0)
        await io.synthesizing(1, 1)
        await io.clause_queued(1, 1)
        await io.ending()
        with pytest.raises(RuntimeError, match="FIX: "):
            await io.clause_played(1, 1)
        await io.close()

    asyncio.run(drive())
    cut = emitted(io, AgentSpeechEnded)[-1]
    frame = io.setup.language.echo_frame
    assert cut.turn_id == 0 and 0 < cut.played_fraction < 1
    assert cut.played_fraction == len(frame) / (len(frame) + len(HEARD))
    assert io.commands.commands[-1] == HangUp(reason="caller_left")


def test_at_the_idle_limit_the_ended_notice_plays_then_the_call_hangs_up(
    settings: VoiceSettings,
) -> None:
    """Nothing heard for `limits.idle_s`: the `ended` notice is sent and spoken, then the call
    ends with `idle`. A turn still open at the limit holds it off, and a turn heard moves it."""
    limits = LimitSettings(max_call_s=600.0, idle_s=10.0)
    io, _ = call(settings.model_copy(update={"limits": limits}))

    async def drive() -> None:
        await greeted(io)
        await io.clock.advance(5.0)
        await io.turn_opened(0)  # heard: the limit moves on, and waits while the turn is open
        await io.clock.advance(15.0)
        assert not sent(io, Notice)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, None)
        await io.clock.advance(9.0)
        assert not sent(io, Notice)
        await io.clock.advance(2.0)
        assert [n.kind for n in sent(io, Notice)] == ["ended"]
        await play(io, 1)
        await io.close()

    asyncio.run(drive())
    (notice,) = speaks(io, 1)
    assert notice.audio is not None and notice.text == io.setup.language.notices["ended"]
    assert io.commands.commands[-2:] == [Send_ended("idle"), HangUp(reason="idle")]
    assert report(io).ended_by == "idle"


def test_an_ended_notice_that_fails_still_ends_the_call(settings: VoiceSettings) -> None:
    limits = LimitSettings(max_call_s=5.0, idle_s=60.0)
    io, _ = call(settings.model_copy(update={"limits": limits}))

    async def drive() -> None:
        await greeted(io)
        await io.clock.advance(limits.max_call_s)
        await turn(io, 0, HEARD)  # heard while the call is ending: not said back
        await io.clause_queued(1, 0)
        await io.clause_failed(1, 0)
        await io.close()

    asyncio.run(drive())
    assert [s.reply_id for s in speaks(io)] == [0, 1]
    assert [n.kind for n in sent(io, Notice)] == ["ended"]  # no `error` while ending
    assert io.commands.commands[-1] == HangUp(reason="max_call")


def test_a_stream_that_ends_with_no_end_reports_the_server_and_nothing_after(
    settings: VoiceSettings,
) -> None:
    """The Pipecat side ends the stream with no end (a fault of its own): the report says
    `server`, and an event or a second close changes nothing; an event after the end is read
    only for a request's report."""
    io, session = call(settings)
    given: list[int] = []

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await session.aclose()
        given.append(len(io.commands.commands))
        await session.aclose()
        await session.handle(Connected(at=io.clock.now()))
        await session.handle(TurnOpened(turn_id=1, at=io.clock.now(), speech_at=io.clock.now()))

    asyncio.run(drive())
    assert report(io).ended_by == "server" and not io.commands.of(HangUp)
    assert given == [len(io.commands.commands)]  # no command after the stream's end
    (record,) = report(io).turns
    assert not record.unfinished and emitted(io, AgentSpeechEnded)[-1].played_fraction == 0.0
