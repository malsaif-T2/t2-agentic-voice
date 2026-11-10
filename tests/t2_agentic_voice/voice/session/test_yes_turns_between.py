"""What comes between an action's read-back and the caller's answer, end to end in the session on
the real yes rule and its words (GP-08; docs/SECURITY.md, invariant 1; voice/session/read_back.py's
`handed`, action_job.py's `flush`; plan 007): a turn begun in the gap before the read-back's first
audio, the summary playing whole over it, declines it as a correction when its words reach the
talker, whether its own transcript or its early start hands them on, so a later yes to the
talker's reply confirms nothing; and an earlier action's outcome landing while a second
read-back waits for its answer is not said until that answer has been taken, so the caller's yes
or thanks to the outcome never confirms the second action. The talker and the port are fakes."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import ReplyDone
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import DeclinedAction, TalkerTurn
from t2_agentic_voice.core.events import ActionCompleted, ConfirmationAnswered
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.text.invisible import provider_text

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import ACTION, PLAN, asked, read_whole
from tests.t2_agentic_voice.voice.session.session_support import emitted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import Step, answer, settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    OUTCOME,
    FakeJobs,
    confirm_call,
    play_reply,
    read_back_played,
)

OTHER_WORDS = "made-up other question about opening hours"
SECOND = PLAN.model_copy(
    update={
        "action": "hand_off_made_up",
        "tool_call_id": "call-2",
        "draft_json": '{"reason": "made-up reason"}',
        "summary": SpokenLine(text="Made-up second summary.", spoken="Made-up second summary."),
    }
)


def _said(io: FakeSessionIO, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


@pytest.mark.parametrize("start", ["transcript", "early"])
def test_a_turn_begun_in_the_gap_before_the_read_back_declines_it_on_the_real_rules(
    settings: VoiceSettings, start: str
) -> None:
    """Invariant 1: the turn opened before the read-back's first audio is no overlap, the
    summary and question play whole over it, and its words reach the talker, by its own
    transcript or by its early start once the read-back ended: the action declined as a
    correction, confirming ended, and the caller's later yes to the talker's reply is the
    talker's turn, never a yes to the old draft."""
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings, jobs)

    async def drive() -> None:
        await asked(io)
        await io.turn_opened(1)  # in the gap: nothing of the read-back has played yet
        await read_whole(io)  # the summary and the question play whole over the caller
        await settle()
        if start == "early":
            await io.turn_held(1)
            await io.transcribing(1, part="held")
            await io.clock.advance(0.3)
            await io.transcribed(1, OTHER_WORDS, language="en", part="held")
            await settle()
            assert [t.turn_id for t in talker.turns] == [0, 1]  # the early start
            assert not session._confirming.active
            await io.turn_closed(1)
        else:
            await io.turn_closed(1)
            await io.transcribing(1)
        await io.transcribed(1, OTHER_WORDS, language="en")
        await settle()
        assert not session._confirming.active
        await play_reply(io, 2)  # the talker's answer to the other question
        await io.clock.advance(1.0)
        await talked(io, 2, "yes")

    asyncio.run(drive())
    assert 1 not in io.overlaps
    handed = talker.turns[1]
    assert handed.turn_id == 1
    assert handed.declined == DeclinedAction(action=ACTION, kind="correction", words=OTHER_WORDS)
    assert emitted(io, ConfirmationAnswered) == [] and jobs.runs == []
    assert [t.turn_id for t in talker.turns] == [0, 1, 2]  # the yes went to the talker


def _two_actions(turn: TalkerTurn) -> Sequence[Step]:
    """Turn 0's reply reads `PLAN` back, turn 2's reads `SECOND` back; any other turn's says
    one clause."""
    if turn.turn_id == 0:
        return [ReadBackRequested(plan=PLAN), ReplyDone()]
    if turn.turn_id == 2:
        return [ReadBackRequested(plan=SECOND), ReplyDone()]
    return answer("Made-up answer.")


@pytest.mark.parametrize("reply", ["yes", "no"])
def test_an_earlier_outcome_waits_while_a_second_read_back_waits_for_its_answer(
    settings: VoiceSettings, reply: str
) -> None:
    """Invariant 1: the first action's write ends after the second read-back played whole; its
    outcome is not said between that read-back's closing question and the caller's answer, so
    the caller's answer is to the question; it is said once that answer's reply has played."""
    jobs = FakeJobs(seconds=6.0)
    io, session, _ = confirm_call(settings, jobs, _two_actions)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, "yes")  # the first action confirmed: its sending line is reply 2
        await play_reply(io, 2)
        await io.clock.advance(0.5)
        await talked(io, 2, "made-up second request")  # the second read-back is reply 3
        await play_reply(io, 3)
        await io.clock.advance(5.0)  # the first write ends: its outcome lands
        await settle()
        assert jobs.finished == 1 and len(emitted(io, ActionCompleted)) == 1
        assert session._confirming.active and speaks(io, 4) == []  # nothing said while it waits
        await talked(io, 3, reply)  # the answer to the second read-back's question
        await play_reply(io, 4)

    asyncio.run(drive())
    answered = [(e.turn_id, e.action, e.decision) for e in emitted(io, ConfirmationAnswered)]
    second = (3, SECOND.action, "yes" if reply == "yes" else "declined")
    assert answered == [(1, ACTION, "yes"), second]
    assert _said(io, 4) != [provider_text(OUTCOME.spoken)]  # the answer's own reply first
    assert _said(io, 5) == [provider_text(OUTCOME.spoken)]
    outcome = session.playback.reply(5)
    assert outcome is not None and outcome.turn_id is None
    ran = [(run.confirmed.action, run.turn_id) for run in jobs.runs]
    assert ran == [(ACTION, 1)] + ([(SECOND.action, 3)] if reply == "yes" else [])
