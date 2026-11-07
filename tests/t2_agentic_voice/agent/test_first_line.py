"""The first line of every request (agent/prompt.py's `FIRST_LINE`, agent/turn.py; plan 006, the
owner's Q21): each request's system message opens with a line new on every request, so no two
requests share a prefix the provider has cached: two requests of one turn, two turns of one
call, and two `TextCall`s, whose call id is the same. With `llm.vary_first_line` off the system
message is the composed prompt as it is, and `render_prompt` never shows the line."""

from __future__ import annotations

import asyncio
import itertools
import re
from datetime import date

import pytest
from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.agent import prompt
from t2_agentic_voice.agent.prompt import compose_prompt, render_prompt
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.evals import ScriptedLLM, TextCall
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    agent,
    call,
    calls,
    reply,
    said,
    talker,
)
from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.testing.text_call_support import AGENT

TURN = TalkerTurn(turn_id=1, words="How do I reset my password?", language="en")
LINE = re.compile(r"Request [0-9a-f]{8}\.")
PASSAGE = Passage(id="made-up-001", title="Reset a password", text="Open the portal.", score=0.7)


def _system(model: FakeChat | ScriptedLLM, index: int) -> str:
    return model.requests[index].messages[0].content


def _first_lines(model: FakeChat | ScriptedLLM) -> list[str]:
    """Each request's first line, checked to be one of `FIRST_LINE`'s."""
    lines = [_system(model, index).split("\n", 1)[0] for index in range(len(model.requests))]
    assert all(LINE.fullmatch(line) for line in lines), lines
    return lines


def _prompt(today: date) -> str:
    return compose_prompt(agent(), language="en", today=today)


def test_the_two_requests_of_a_turn_open_with_different_first_lines() -> None:
    search = knowledge_tool(FakeKnowledgeBase([PASSAGE]), description="Search the help.")
    model = FakeChat(calls(call(NAME, query="reset my password")), said("Open the portal."))
    clock = FakeClock()
    reply(talker(model, search, clock=clock), TURN)
    first, second = _first_lines(model)
    assert first != second
    today = clock.wall().date()
    composed = compose_prompt(agent(search), language="en", today=today)
    assert [_system(model, i).split("\n", 1)[1] for i in (0, 1)] == [composed, composed]


def test_two_turns_of_one_call_open_with_different_first_lines() -> None:
    model = FakeChat(said("Sure."), said("Sure."))
    chat = talker(model)
    reply(chat, TURN)
    heard = Conversation(turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered"),))
    reply(chat, TalkerTurn(turn_id=2, words="and then?", language="en", conversation=heard))
    first, second = _first_lines(model)
    assert first != second


def test_two_text_calls_open_with_different_first_lines() -> None:
    """A `TextCall`'s call id is always the same: the line is never made of it."""
    llm = ScriptedLLM([list(ScriptedLLM.reply("First.")), list(ScriptedLLM.reply("Second."))])

    async def scene(words: str) -> None:
        async with TextCall(AGENT, llm=llm, language="en") as call:
            await call.user(words)
            await call.advance(5.0)

    asyncio.run(scene("Hello?"))
    asyncio.run(scene("Hello?"))
    first, second = _first_lines(llm)
    assert first != second


def test_the_line_takes_its_id_from_a_source_a_test_can_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = itertools.count(41)
    monkeypatch.setattr(prompt, "request_id", lambda: f"{next(ids):08x}")
    model = FakeChat(said("Sure."))
    clock = FakeClock()
    reply(talker(model, clock=clock), TURN)
    assert prompt.FIRST_LINE.format(id="00000029") == "Request 00000029."
    assert _system(model, 0) == f"Request 00000029.\n{_prompt(clock.wall().date())}"


def test_the_default_ids_differ_on_every_request() -> None:
    """A count from a random start: no two of one process the same, whatever the start."""
    made = [prompt.request_id() for _ in range(1000)]
    assert len(set(made)) == 1000
    assert all(re.fullmatch(r"[0-9a-f]{8}", each) for each in made)


def test_with_the_setting_off_the_system_message_is_the_composed_prompt() -> None:
    settings = VoiceSettings(env="test", llm=LlmSettings(vary_first_line=False))
    model = FakeChat(said("Sure."), said("Sure."))
    clock = FakeClock()
    chat = talker(model, clock=clock, settings=settings)
    reply(chat, TURN)
    reply(chat, TalkerTurn(turn_id=2, words="and then?", language="en"))
    composed = _prompt(clock.wall().date())
    assert [_system(model, 0), _system(model, 1)] == [composed, composed]


def test_the_setting_is_on_by_default() -> None:
    assert VoiceSettings(env="test").llm.vary_first_line is True


def test_render_prompt_shows_the_prompt_without_the_line() -> None:
    """What a team reads: the composed prompt of today, never a request's first line."""
    shown = render_prompt(agent(), "en")
    assert shown.startswith("You are the voice of a support call.")
    assert not LINE.match(shown)
