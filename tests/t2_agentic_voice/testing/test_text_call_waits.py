"""A `TextCall`'s wait for a moment of the agent's (testing/text_side.py's `TextDriver.until`;
plan 010, run F's plays stuck on the agent's turn): it gives up at once when the call has
ended, since no moment of its comes then, rather than after `MAX_WAIT_S`."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.testing.text_side import MAX_WAIT_S

from tests.t2_agentic_voice.testing.text_call_support import ScriptedCall, Step, answer


def _script(turn: TalkerTurn) -> list[Step]:
    return answer("Sure, which day?")


def test_a_wait_for_a_read_back_ends_when_the_call_ends_idle() -> None:
    settings = VoiceSettings(env="test")
    settings = settings.model_copy(
        update={"limits": settings.limits.model_copy(update={"idle_s": 5.0})}
    )

    async def scene() -> float:
        async with ScriptedCall(_script, settings=settings) as call:
            await call.user("I want to fly to London.")
            began = call._drive().clock.now()
            with pytest.raises(AssertionError, match="the call ended"):
                await call.user("Yes, book it.", during="read_back")
            return call._drive().clock.now() - began

    waited = asyncio.run(scene())
    assert waited < 10.0 < MAX_WAIT_S  # the idle end, not the wait's bound
