"""The session's turns (voice/session/call.py; io.py's turns and drop rule): under
`interruptions.mode = "drop"`, speech that starts while the echo plays, or within 300 ms after
it, is not said back, and speech after that is; a turn's end that comes before its transcript,
with the next turn opening before that transcript (plan 003's appendix, item 6), and a
transcript before its turn's end; an empty transcript said back as nothing and kept on the
timeline; and a failed transcript and a failed echo clause each giving the `error` notice, sent
and spoken from the phrase cache with no request."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ProviderFailed, TurnMetrics, UserTurnEnded
from t2_agentic_voice.voice.protocol import Notice, State
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.playback import DROP_AFTER_S
from t2_agentic_voice.voice.session.session_events import Synthesizing

from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    captions,
    drop,
    emitted,
    greeted,
    play,
    report,
    sent,
    speaks,
    turn,
)


@pytest.mark.parametrize(
    ("after_s", "answered"),
    [(None, False), (0.0, False), (DROP_AFTER_S - 0.05, False), (DROP_AFTER_S + 0.05, True)],
    ids=["during", "at-its-end", "within-300-ms", "after-300-ms"],
)
def test_speech_begun_while_the_echo_plays_or_just_after_is_not_said_back(
    settings: VoiceSettings, after_s: float | None, answered: bool
) -> None:
    """Under `drop`, turn 1's speech begins while turn 0's echo plays (`None`), or `after_s`
    after its last clause played: within 300 ms it is the agent's own voice leaking back, so it
    is not said back, though it is heard and kept; after that it is the caller's, said back."""
    io, _ = call(drop(settings))

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        _, *words = speaks(io, 1)
        await io.clause_queued(1, 0)
        if after_s is None:
            await io.clock.advance(0.1)
            await io.turn_opened(1)  # the caller's speech began in the echo
        for word in words:
            await io.synthesizing(1, word.clause)
            await io.clause_queued(1, word.clause)
            await io.clause_played(1, word.clause)
        await io.clause_played(1, 0)
        if after_s is not None:
            await io.clock.advance(after_s)
            await io.turn_opened(1)
        await io.clock.advance(0.5)
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, "words of the second turn", language="en")
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert bool(speaks(io, 2)) is answered
    assert [c.turn_id for c in captions(io, "caller")] == ([0, 1] if answered else [0])
    record = report(io).turns[1]
    assert (record.dropped, record.heard) == (not answered, "words of the second turn")


def test_a_turns_end_before_its_transcript_and_the_next_turn_opening_first(
    settings: VoiceSettings,
) -> None:
    """Turn 0 closes, then turn 1 opens before turn 0's transcript comes: turn 0 is said back as
    reply 1 when its transcript comes, and turn 1, whose speech began before any echo played,
    as reply 2. Turn 2's transcript comes before its end: it is said back at once, and its
    times go out once it has closed and its echo has played."""
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.turn_opened(1)  # the next turn begins before turn 0's transcript
        await io.transcribed(0, "first words", language="en")
        await io.turn_closed(1)
        await io.transcribing(1)
        await io.transcribed(1, "second words", language="en")
        await play(io, 1)
        await play(io, 2)
        await io.clock.advance(1.0)
        await io.turn_opened(2)
        await io.transcribing(2)
        await io.transcribed(2, "third words", language="en")
        await play(io, 3)
        assert [m.turn_id for m in emitted(io, TurnMetrics)] == [0, 1]
        await io.turn_closed(2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [(s.reply_id, s.turn_id) for s in speaks(io) if s.clause == 0] == [
        (0, None),
        (1, 0),
        (2, 1),
        (3, 2),
    ]
    assert [m.turn_id for m in emitted(io, TurnMetrics)] == [0, 1, 2]
    metrics = emitted(io, TurnMetrics)[0]
    assert metrics.stt_ms is not None and metrics.ttfa_ms is not None
    assert metrics.tts_first_audio_ms is not None
    assert [e.heard for e in emitted(io, UserTurnEnded)] == [
        "first words",
        "second words",
        "third words",
    ]


@pytest.mark.parametrize("heard", ["", "   ", None], ids=["empty", "spaces", "no-audio"])
def test_an_empty_transcript_is_said_back_as_nothing_and_kept(
    settings: VoiceSettings, heard: str | None
) -> None:
    """Nothing heard: no reply, no caption, and the turn kept in the report, heard and said
    empty, the agent listening again."""
    io, _ = call(settings)

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.turn_closed(0)
        if heard is not None:
            await io.transcribing(0)
        await io.transcribed(0, heard)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) == [] and captions(io, "caller") == []
    (record,) = report(io).turns
    assert (record.heard, record.said, record.dropped, record.unfinished) == ("", "", False, False)
    assert sent(io, State)[-1].state == "listening"
    assert emitted(io, UserTurnEnded)[0].heard == ""


def test_a_failed_transcript_gives_the_error_notice_from_the_cache(
    settings: VoiceSettings,
) -> None:
    """The turn's request failed: `ProviderFailed`, then the `error` notice, sent as a message
    and spoken as the next reply from the phrase cache, sending no request."""
    io, _ = call(settings)
    error = io.setup.language.notices["error"]

    async def drive() -> None:
        await greeted(io)
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0)
        await io.transcribed(0, None, failure="timeout", retryable=True)
        await io.clause_queued(1, 0)
        await io.clause_played(1, 0)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert sent(io, Notice) == [Notice(kind="error", text=error)]
    (notice,) = speaks(io, 1)
    assert (notice.text, notice.turn_id) == (error, None) and notice.audio is not None
    assert not [e for e in io.events if isinstance(e, Synthesizing)]
    (failed,) = emitted(io, ProviderFailed)
    assert (failed.kind, failed.retryable, failed.turn_id) == ("timeout", True, 0)
    assert [c.reply_id for c in captions(io)] == [0]  # a notice shows as its message


def test_a_failed_echo_clause_gives_the_error_notice_once(settings: VoiceSettings) -> None:
    """Two of the echo's clauses fail: one `error` notice, queued as the next reply behind the
    echo, which ends with what played."""
    io, _ = call(settings, max_chars=12)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, "one two three four five six seven")
        _, first, second, *rest = speaks(io, 1)
        await io.clause_queued(1, 0)
        await io.clause_played(1, 0)
        for clause in (first, second):
            await io.synthesizing(1, clause.clause)
            await io.clause_failed(1, clause.clause, failure="rate_limited")
        for clause in rest:
            await io.synthesizing(1, clause.clause)
            await io.clause_queued(1, clause.clause)
            await io.clause_played(1, clause.clause)
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [n.kind for n in sent(io, Notice)] == ["error"]
    (notice,) = speaks(io, 2)
    assert isinstance(notice, Speak) and notice.audio is not None
    assert [e.kind for e in emitted(io, ProviderFailed)] == ["rate_limited", "rate_limited"]
    record = report(io).turns[0]
    assert not record.stopped and record.said
