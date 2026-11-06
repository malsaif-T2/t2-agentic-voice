"""The talker's testing kit (testing/llm_fakes.py, knowledge_fake.py, text_call.py; plan 006,
Block 0): the fake knowledge base answers from a test's passages and keeps every search; the fake
chat models are `ChatModel`s that send nothing anywhere, and `TextCall` holds the injections and
expectations the plan's criteria list, their behaviour stubs that raise (Tracks A and C)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatModel, ChatRequest
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase, Passage
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase, KnowledgeSearch
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW, FunctionLLM, ScriptedLLM
from t2_agentic_voice.testing.text_call import TextCall, TextTurn, TurnExpectations

CALLER = Caller(subject="made-up-subject")
RESET = Passage(id="p-1", title="Reset a password", text="Open Settings.", score=0.9)
ARCHIVE = Passage(id="p-2", title="Archive a ticket", text="Press Archive.", score=0.7)
REQUEST = ChatRequest(messages=(ChatMessage.user("hello"),), model="openai/gpt-oss-120b")


def test_the_fake_knowledge_base_answers_from_its_passages_and_keeps_each_search() -> None:
    kb = FakeKnowledgeBase([RESET, ARCHIVE], answers={"archiving": [ARCHIVE]})
    port: KnowledgeBase = kb  # mypy checks the port's shape

    async def searches() -> tuple[list[Passage], ...]:
        return (
            await port.search("password", language="en", caller=CALLER, limit=1),
            await port.search("archiving", language="ar-SA", caller=CALLER, limit=5),
            await FakeKnowledgeBase().search("x", language="ar", caller=CALLER, limit=3),
        )

    assert asyncio.run(searches()) == ([RESET], [ARCHIVE], [])
    assert kb.searches == [
        KnowledgeSearch(query="password", language="en", caller=CALLER, limit=1),
        KnowledgeSearch(query="archiving", language="ar-SA", caller=CALLER, limit=5),
    ]
    with pytest.raises(ValidationError):
        asyncio.run(kb.search("x", language="en", caller=CALLER, limit=0))


def test_the_fake_chat_models_send_nothing_and_their_streams_are_stubs() -> None:
    scripted, function = ScriptedLLM([[]]), FunctionLLM(lambda request: [])
    models: list[ChatModel] = [scripted, function]  # mypy checks the port's shape
    assert [(m.name, m.data_flow) for m in models] == [
        ("scripted", FAKE_DATA_FLOW),
        ("function", FAKE_DATA_FLOW),
    ]
    assert (scripted.script, scripted.requests, function.requests) == (((),), [], [])
    for model in models:
        with pytest.raises(NotImplementedError):
            model.stream(REQUEST)
        asyncio.run(model.aclose())
    with pytest.raises(NotImplementedError):
        ScriptedLLM.reply("Open Settings.")
    with pytest.raises(NotImplementedError):
        ScriptedLLM.call_tool("search_help", query="password")


def test_a_text_call_holds_its_injections_and_expectations_as_stubs() -> None:
    agent = VoiceAgent(
        name="helper", languages=[Language.english(greeting="Hi")], instructions="Be brief."
    )
    call = TextCall(agent, llm=ScriptedLLM([]), language="en")
    assert (call.agent, call.language, call.chars_per_second) == (agent, "en", 15.0)

    async def scene() -> None:
        with pytest.raises(NotImplementedError):
            await call.__aenter__()
        with pytest.raises(NotImplementedError):
            await call.__aexit__(None, None, None)
        for step in (
            call.user("How do I reset my password?"),
            call.user("stop", during="agent_speaking"),
            call.user("actually, archiving", at="tool_running"),
            call.advance(1.5),
            call.stop(),
        ):
            with pytest.raises(NotImplementedError):
                await step

    asyncio.run(scene())
    with pytest.raises(NotImplementedError):
        _ = call.violations
    with pytest.raises(NotImplementedError):
        _ = TextTurn().expect
    expect = TurnExpectations()
    checks: list[Callable[[], None]] = [
        lambda: expect.tool_call("search_help", query="password"),
        lambda: expect.said(contains="Settings"),
        expect.blocked,
        lambda: expect.cancelled("search_help"),
        lambda: expect.language("en"),
    ]
    for check in checks:
        with pytest.raises(NotImplementedError):
            check()
