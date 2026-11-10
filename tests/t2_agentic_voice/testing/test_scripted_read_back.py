"""A read-back in the tests' scripted talker (text_call_support.py's `Asked`; plan 007, Track D):
its plan is kept where the text call finds it and never handed to the session, which plays only
the clauses the script says and hands the caller's next words to the talker, so the tests of
test_text_call_actions.py hold whether or not the session reads a read-back back itself and
confirms (Track C's)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.testing.text_read_back import readings
from t2_agentic_voice.testing.text_watch import plans_of
from t2_agentic_voice.voice.session.talker_play import Talk, TalkPlayer

from tests.t2_agentic_voice.testing.action_support import agent_with, plan_of, read_back_steps
from tests.t2_agentic_voice.testing.text_call_support import ScriptedCall, Step, answer

PLAN = plan_of()
REQUEST = "book room R-204"


def _script(turn: TalkerTurn) -> list[Step]:
    return read_back_steps(PLAN) if turn.turn_id == 0 else answer(PLAN.asked_again.text)


def test_a_plan_is_kept_from_the_session_and_found_by_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handed: list[TalkerEvent] = []
    play = TalkPlayer.play

    async def spy(self: TalkPlayer, talk: Talk, event: TalkerEvent, at: float) -> None:
        handed.append(event)
        await play(self, talk, event, at)

    monkeypatch.setattr(TalkPlayer, "play", spy)

    async def scene() -> tuple[int, list[str]]:
        async with ScriptedCall(_script, agent=agent_with()) as call:
            await call.user(REQUEST)
            await call.advance(10.0)
            await call.user("yes")
            await call.advance(10.0)
            assert plans_of(call._watched) == (PLAN,) and call.talker is not None
            found = readings(call._parts()[1].playback, plans_of(call._watched))
            return len(found), [turn.words for turn in call.talker.turns]

    read, answered = asyncio.run(scene())
    assert read == 1 and answered == [REQUEST, "yes"]  # the yes went to the talker
    assert not [e for e in handed if isinstance(e, ReadBackRequested)]
    assert PLAN.summary.text in [e.text for e in handed if isinstance(e, SpokenClause)]
