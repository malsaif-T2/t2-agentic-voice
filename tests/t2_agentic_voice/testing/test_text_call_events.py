"""`TextCall.emitted` (testing/text_call.py): the call's public events so far, in order, as the
runtime's observers get them, read while the call runs (as an app's tool reads them, the flight
app's lean booking check) and once it has ended; a copy, which the caller cannot change."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.evals import TextCall
from t2_agentic_voice.events import AgentSpeechEnded, CallEnded, CallStarted, Event, UserTurnEnded

from tests.t2_agentic_voice.testing.text_call_support import NoModel


def test_the_calls_events_are_read_in_order_while_it_runs_and_after() -> None:
    agent = VoiceAgent(name="echo-events", languages=[Language.english(greeting="Hi.")])

    async def scene() -> tuple[tuple[Event, ...], tuple[Event, ...]]:
        async with TextCall(agent, llm=NoModel()) as call:
            await call.user("check the line please")
            await call.advance(10.0)
            during = call.emitted
        return during, call.emitted

    during, after = asyncio.run(scene())
    assert any(isinstance(e, CallStarted) for e in during)
    heard = [e for e in during if isinstance(e, UserTurnEnded)]
    assert [(e.turn_id, e.heard) for e in heard] == [(0, "check the line please")]
    spoke = [e for e in during if isinstance(e, AgentSpeechEnded)]
    assert spoke[0].turn_id is None  # the greeting
    echoed = spoke[-1]
    assert echoed.turn_id == 0 and "check the line please" in echoed.text
    assert echoed.played_fraction == 1.0
    assert during.index(heard[0]) < during.index(echoed)
    assert after[: len(during)] == during
    assert any(isinstance(e, CallEnded) for e in after[len(during) :])
