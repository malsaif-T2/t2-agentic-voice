"""The most model requests one turn makes (agent/turn.py, `llm.max_requests_per_turn`): each
but the last offers the agent's tools, the last none, so the turn ends in words. Three by
default, as before (test_talker_tools.py's three requests at most); four when set, the fourth
with no tools, the tool call it makes anyway not run. A model that answers in words sooner
sends no more."""

from __future__ import annotations

from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.llm import LlmSettings

from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    call,
    calls,
    kinds,
    reply,
    said,
    talker,
)

TURN = TalkerTurn(turn_id=1, words="Hold a seat on the made-up flight.", language="en")
ran: list[str] = []


@tool(description="Do a made-up step.")
async def step(label: str) -> dict[str, str]:
    ran.append(label)
    return {"done": label}


def _calling(count: int) -> FakeChat:
    return FakeChat(*(calls(call("step", f"c-{n}", label=f"s{n}")) for n in range(1, count + 1)))


def test_the_default_is_three_requests_the_last_with_no_tools() -> None:
    assert LlmSettings().max_requests_per_turn == 3
    ran.clear()
    model = _calling(3)
    events = reply(talker(model, step), TURN)
    assert [len(r.tools) for r in model.requests] == [1, 1, 0]
    assert ran == ["s1", "s2"] and kinds(events)[-1] == "ReplyDone"


def test_four_when_set_the_fourth_with_no_tools() -> None:
    four = VoiceSettings(env="test", llm=LlmSettings(max_requests_per_turn=4))
    ran.clear()
    model = _calling(4)
    events = reply(talker(model, step, settings=four), TURN)
    assert [len(r.tools) for r in model.requests] == [1, 1, 1, 0]
    assert ran == ["s1", "s2", "s3"] and kinds(events).count("ModelRequested") == 4
    ran.clear()
    model = FakeChat(calls(call("step", label="s1")), said("Held."))
    events = reply(talker(model, step, settings=four), TURN)
    assert ran == ["s1"] and len(model.requests) == 2
