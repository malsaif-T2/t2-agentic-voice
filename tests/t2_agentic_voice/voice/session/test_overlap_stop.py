"""What a stop does to the reply's work and to the heard history (voice/session/speaker.py,
scope.py, history.py): a stop, the overlap rule's or the caller's own, cancels the reply's scope,
which holds a slow model stream and a slow lookup (tests/t2_agentic_voice/responder_fakes.py),
both within 100 ms on the fake clock, and leaves no task of the call, while work started outside
it goes on; a clause cut while it plays keeps the share of its audio sent, from the output's taps,
against its length estimated from the clauses played, which `AgentSpeechEnded`, the turn's fate
and the report read, at a stop and at the call's end; a request's report after a stop is still
counted (TD-055); and under `interruptions.mode = "drop"`, a turn over the echo gives the drop
rule's commands. The rule is a fake (conftest.py's `rule`)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, UserTurnEnded
from t2_agentic_voice.voice.protocol import Caption, Duck, State, Unduck
from t2_agentic_voice.voice.session.commands import HearOverlap, Send, StopSpeaking
from t2_agentic_voice.voice.session.echo import again
from t2_agentic_voice.voice.session.session_events import Synthesizing

from tests.t2_agentic_voice.responder_fakes import SlowResponder
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    STOP_TEXT,
    FakeRule,
    echo_playing,
    two_step,
)
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    drop,
    emitted,
    greeted,
    report,
    sent,
    speaks,
    turn,
)


@pytest.mark.parametrize("by", ["overlap", "client"])
def test_a_stop_cancels_the_replys_slow_stream_and_lookup_within_100_ms_leaving_no_task(
    settings: VoiceSettings, rule: FakeRule, by: str
) -> None:
    io, session = call(two_step(settings))
    responder = SlowResponder(io.clock, chunk_s=0.3, lookup_s=5.0)
    outside = SlowResponder(io.clock, lookup_s=1.0)

    async def drive() -> None:
        await echo_playing(io)
        scope = session._speaker.scope(1)
        model = scope.start(responder.read(), name="model")
        lookup = scope.start(responder.lookup("made-up order"), name="lookup")
        write = asyncio.create_task(outside.lookup("made-up write"))  # an action's, outside
        await asyncio.sleep(0)
        if by == "overlap":
            await io.turn_opened(1)
            await io.transcribing(1, audio_s=0.75, part="window")
        await io.clock.advance(0.2)
        stopped_at = io.clock.now()
        if by == "overlap":
            await io.transcribed(1, STOP_TEXT, language="en", part="window")
        else:
            await io.client({"v": 1, "type": "stop"})
        assert set(responder.cancelled) == {"stream", "lookup"}
        assert max(responder.cancelled.values()) - stopped_at <= 0.1
        assert model.cancelled() and lookup.cancelled()
        assert scope.cancelled and scope.running == 0 and not write.done()
        await io.clock.advance(1.0)
        assert write.result() == "found for made-up write"  # never cancelled by the scope
        await io.ending()
        await io.close()
        assert asyncio.all_tasks() == {asyncio.current_task()}  # no task of the call left

    asyncio.run(drive())
    assert io.commands.of(StopSpeaking) == [StopSpeaking(reply_id=1)]
    assert responder.finished == {}


async def _words_playing(io: FakeSessionIO, *, frame_s: float, words_s: float) -> None:
    """The greeting played (0.5 s), the echo's frame played (`frame_s`), and `words_s` of its
    heard words' audio sent while they play."""
    await greeted(io)
    await turn(io, 0, HEARD)
    await io.clause_queued(1, 0)
    await io.agent_audio(frame_s)
    await io.clause_played(1, 0, audio_s=frame_s)
    await io.synthesizing(1, 1)
    await io.clause_queued(1, 1)
    await io.agent_audio(words_s)


@pytest.mark.parametrize("end", ["stop", "call-end"])
def test_a_clause_cut_while_it_plays_keeps_the_share_of_its_audio_sent(
    settings: VoiceSettings, end: str
) -> None:
    """The heard words were cut halfway through their estimated length (seconds per caption
    character, from the greeting and the frame played): the history marks the frame played and
    the words cut at that share; `AgentSpeechEnded` counts it by characters; the turn's reply
    was cut after a clause played, and the report's `said` holds what the caller heard."""
    io, session = call(settings)
    frame = io.setup.language.echo_frame
    greeting = io.setup.language.greeting
    rate = (0.5 + 0.3) / (len(greeting) + len(frame))
    words_s = 0.5 * rate * len(HEARD)

    async def drive() -> None:
        await _words_playing(io, frame_s=0.3, words_s=words_s)
        if end == "stop":
            await io.client({"v": 1, "type": "stop"})
        await io.ending()
        await io.close()

    asyncio.run(drive())
    played, cut = session.history.reply(1).clauses
    assert (played.fate, played.played_fraction, cut.fate) == ("played", 1.0, "cut")
    assert cut.played_fraction == pytest.approx(0.5, rel=1e-3)
    spoke = emitted(io, AgentSpeechEnded)[-1]
    share = (len(frame) + 0.5 * len(HEARD)) / (len(frame) + len(HEARD))
    assert spoke.turn_id == 0 and spoke.played_fraction == pytest.approx(share, rel=1e-3)
    assert session.history.turns()[0].fate == "cut"
    record = report(io).turns[0]
    assert record.said == f"{frame} {HEARD}" and record.stopped is (end == "stop")


def test_a_clause_cut_before_any_played_is_measured_at_a_calm_rate(settings: VoiceSettings) -> None:
    """With no clause played yet in the call (the phrase cache lacks the greeting), a cut
    clause's length is estimated at `SECONDS_PER_CHARACTER`."""
    from t2_agentic_voice.voice.session.speaker import SECONDS_PER_CHARACTER

    from tests.t2_agentic_voice.fakes import FakePhrases

    io, session = call(settings, phrases=FakePhrases())

    async def drive() -> None:
        await io.connected()
        await turn(io, 0, HEARD)  # its echo is reply 0: no greeting, no frame
        await io.synthesizing(0, 0)
        await io.clause_queued(0, 0)
        await io.agent_audio(0.25 * SECONDS_PER_CHARACTER * len(HEARD))
        await io.client({"v": 1, "type": "stop"})
        await io.ending()
        await io.close()

    asyncio.run(drive())
    (cut,) = session.history.reply(0).clauses
    assert cut.fate == "cut" and cut.played_fraction == pytest.approx(0.25, rel=1e-3)
    assert session.history.turns()[0].fate == "rolled_back"


def test_a_requests_report_after_a_stop_is_still_counted(settings: VoiceSettings) -> None:
    """The heard words' request went just before the stop, its report handed after it
    (TD-055): counted, its reply still ended once."""
    io, session = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.client({"v": 1, "type": "stop"})
        await session.handle(Synthesizing(reply_id=1, clause=1, at=io.clock.now()))
        await io.ending()
        await io.close()

    asyncio.run(drive())
    tts = report(io).usage[1]
    assert (tts.requests, tts.characters) == (1, len(speaks(io, 1)[1].text))
    assert [e.turn_id for e in emitted(io, AgentSpeechEnded)] == [None, 0]


def test_under_drop_a_turn_over_the_echo_and_a_stop_give_the_drop_rules_commands(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """Under `drop`, set here since `two_step` is the default: the turn over the echo gives no
    command and is not said back, not judged, and kept dropped; the caller's `stop` gives
    `StopSpeaking` and the state alone."""
    io, session = call(drop(settings))

    async def drive() -> None:
        await echo_playing(io)
        given = len(io.commands.commands)
        await io.turn_opened(1)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, STOP_TEXT, language="en")
        assert len(io.commands.commands) == given
        await io.client({"v": 1, "type": "stop"})
        assert io.commands.commands[given:] == [
            StopSpeaking(reply_id=1),
            Send(message=State(state="listening")),
        ]
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert rule.judged == [] and io.commands.of(HearOverlap) == []
    assert sent(io, Duck) == [] and sent(io, Unduck) == []
    assert not [c for c in sent(io, Caption) if c.cut]
    assert report(io).turns[1].dropped and [e.turn_id for e in emitted(io, UserTurnEnded)] == [0]
    assert session.history.turns()[1].fate == "dropped"


def test_nothing_heard_is_said_again_and_a_phrase_the_cache_lacks_goes_unsaid(
    settings: VoiceSettings,
) -> None:
    io, session = call(settings)

    async def drive() -> None:
        assert await session._speaker.repeat(1.0, turn_id=0) is None

    asyncio.run(drive())
    lines = again(
        io.setup, [("not a declared phrase", True), ("made-up words", False)], reply_id=3, turn_id=1
    )
    assert [(line.speak.clause, line.speak.text, line.speak.audio) for line in lines] == [
        (0, "made-up words", None)
    ]
