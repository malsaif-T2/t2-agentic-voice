"""The progress line in the call (voice/session/talking.py's progress line; plan 006, Q27): said
`after_s` after the caller stopped speaking if no answer has begun, whatever the reply is waiting
on by then, and never once one has. The fake talker is the tests' own (talker_support.py)."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.agent.talker import (
    ProgressDue,
    ReplyDone,
    SpokenClause,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import greeted, play, report, speaks
from tests.t2_agentic_voice.voice.session.talker_support import (
    AGENT,
    PROGRESS,
    Script,
    Step,
    Work,
    answer,
    settle,
    talked,
    talker_call,
)

AFTER_S = 2.0
ASKED = "Where is my ticket?"
FOUND = "Found it."
LINE = ProgressDue(tool="search_help", key="looking", language="en", after_s=AFTER_S)


def _said(io: FakeSessionIO) -> list[str]:
    return [s.text for s in speaks(io, 1)]


def _due_in(settings: VoiceSettings) -> float:
    """How long after the turn is heard the line falls due: its detector's stop came late."""
    return AFTER_S - settings.turns.vad_stop_ms / 1000


async def _end(io: FakeSessionIO) -> None:
    await io.ending()
    await io.close()


async def _asked(io: FakeSessionIO) -> None:
    await greeted(io)
    await talked(io, 0, ASKED)


async def _moved(io: FakeSessionIO, seconds: float) -> None:
    await io.clock.advance(seconds)
    await settle()


def _call(settings: VoiceSettings, script: Script) -> tuple[FakeSessionIO, CallSession]:
    io, session, _ = talker_call(settings, script)
    return io, session


def test_the_line_is_said_at_its_time_though_the_search_is_over_and_the_model_still_writes(
    settings: VoiceSettings,
) -> None:
    """What the caller waits on at that time does not matter: here the tool ended long before,
    and the second model request is what takes the time."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [
            ToolBegan(call_id="t-1", tool="search_help"),
            LINE,
            ToolEnded(call_id="t-1", tool="search_help", ok=True, ms=100.0),
            Work(5.0),
            *answer(FOUND),
        ]

    io, _ = _call(settings, script)
    due = _due_in(settings)

    async def drive() -> None:
        await _asked(io)
        await _moved(io, due - 0.01)
        assert _said(io) == []
        await _moved(io, 0.01)
        assert _said(io) == [PROGRESS["en"]]
        await _moved(io, 5.0)
        assert _said(io) == [PROGRESS["en"], FOUND]
        await play(io, 1)
        await _end(io)

    asyncio.run(drive())
    assert report(io).turns[0].times.progress_ms is not None


def test_an_answer_begun_before_the_time_says_no_line(settings: VoiceSettings) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [LINE, Work(0.5), *answer(FOUND)]

    io, _ = _call(settings, script)
    due = _due_in(settings)

    async def drive() -> None:
        await _asked(io)
        await _moved(io, 0.5)
        assert _said(io) == [FOUND]
        await _moved(io, due)
        assert _said(io) == [FOUND]
        await play(io, 1)
        await _end(io)

    asyncio.run(drive())


def test_a_tool_that_begins_past_the_time_says_the_line_at_once(settings: VoiceSettings) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [Work(3.0), LINE, Work(1.0), *answer(FOUND)]

    io, _ = _call(settings, script)

    async def drive() -> None:
        await _asked(io)
        await _moved(io, 3.0)
        assert _said(io) == [PROGRESS["en"]]
        await _moved(io, 1.0)
        await play(io, 1)
        await _end(io)

    asyncio.run(drive())


def test_a_tool_that_begins_past_the_time_after_a_clause_says_no_line(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [
            SpokenClause(text="Let me look.", language="en"),
            Work(3.0),
            LINE,
            Work(1.0),
            *answer(FOUND),
        ]

    io, _ = _call(settings, script)

    async def drive() -> None:
        await _asked(io)
        await _moved(io, 4.0)
        assert _said(io) == ["Let me look.", FOUND]
        await play(io, 1)
        await _end(io)

    asyncio.run(drive())


def test_a_reply_that_ended_with_no_clause_says_its_notice_and_no_line_after(
    settings: VoiceSettings,
) -> None:
    def script(turn: TalkerTurn) -> list[Step]:
        return [LINE, ReplyDone()]

    io, _ = _call(settings, script)
    due = _due_in(settings)

    async def drive() -> None:
        await _asked(io)
        notice = AGENT.languages[0].notices["error"]
        assert _said(io) == [notice]
        await _moved(io, due + 1.0)
        assert _said(io) == [notice]
        await play(io, 1)
        await _end(io)

    asyncio.run(drive())


def test_a_reply_kept_behind_a_newer_turn_says_no_line(settings: VoiceSettings) -> None:
    """While a newer turn of the caller's is open, nothing more of the reply plays
    (talking.py's kept reply), the line included."""

    def script(turn: TalkerTurn) -> list[Step]:
        return [LINE, Work(9.0), *answer(FOUND)]

    io, _ = _call(settings, script)
    due = _due_in(settings)

    async def drive() -> None:
        await _asked(io)
        await io.turn_opened(1)
        await _moved(io, due + 0.1)
        assert _said(io) == []
        await _end(io)

    asyncio.run(drive())
