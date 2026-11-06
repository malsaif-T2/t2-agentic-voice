"""The talker's testing kit (testing/llm_fakes.py, knowledge_fake.py, text_call.py,
turn_data.py; plan 006, Block 0): the fake knowledge base answers from a test's passages and keeps
every search; the fake chat models are `ChatModel`s that send nothing anywhere, and `TextCall`
holds the injections and expectations the plan's criteria list, and each turn what it did as
data, for a runner to score (the clauses heard, the tool calls, the cards, the blocked clauses,
the times and the usage), their behaviour stubs that raise (Tracks A and C)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatModel, ChatRequest, Usage
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase, Passage
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase, KnowledgeSearch
from t2_agentic_voice.testing.llm_fakes import FAKE_DATA_FLOW, FunctionLLM, ScriptedLLM
from t2_agentic_voice.testing.text_call import TextCall, TextTurn, TurnExpectations
from t2_agentic_voice.testing.turn_data import BlockedClause, HeardClause, TextToolCall

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
    assert (call.clock, TextCall(agent, llm=ScriptedLLM([]), clock="system").clock) == (
        "virtual",
        "system",
    )

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


def test_a_text_turn_gives_what_it_did_as_data_its_reads_stubs() -> None:
    cut = HeardClause(text="Open Settings.", language="en", fate="cut", played_fraction=0.4)
    progress = HeardClause(
        text="One moment.", language="en", fate="played", played_fraction=1.0, phrase=True
    )
    search = TextToolCall(
        call_id="c-1", tool="search_help", arguments={"query": "password"}, outcome="ok", ms=840.0
    )
    running = TextToolCall(call_id="c-2", tool="search_help", outcome="running")
    blocked = BlockedClause(text="Your number is 4521.", language="en", unsupported=("4521",))
    assert (cut.phrase, progress.phrase) == (False, True)
    assert (search.arguments, running.arguments, running.ms) == ({"query": "password"}, {}, None)
    assert blocked.unsupported == ("4521",)
    with pytest.raises(TypeError):
        search.arguments["query"] = "other"  # type: ignore[index]
    with pytest.raises(ValidationError):
        cut.text = "other"  # type: ignore[misc]
    turn = TextTurn()
    reads: list[Callable[[], object]] = [
        lambda: turn.fate,
        lambda: turn.clauses,
        lambda: turn.tool_calls,
        lambda: turn.cards,
        lambda: turn.blocked,
        lambda: turn.first_token_s,
        lambda: turn.first_clause_s,
        lambda: turn.model_requests,
        lambda: turn.usage,
    ]
    for read in reads:
        with pytest.raises(NotImplementedError):
            read()
    # The types a runner reads them as (mypy checks the properties' shapes).
    shapes: tuple[type[object], ...] = (HeardClause, TextToolCall, BlockedClause, Card, Usage)
    assert all(isinstance(shape, type) for shape in shapes)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (HeardClause, {"text": "x", "language": "en", "fate": "played", "played_fraction": 0.5}),
        (HeardClause, {"text": "x", "language": "en", "fate": "unplayed", "played_fraction": 1}),
        (HeardClause, {"text": "x", "language": "fr", "fate": "cut", "played_fraction": 0.5}),
        (HeardClause, {"text": "x", "language": "en", "fate": "said", "played_fraction": 1}),
        (TextToolCall, {"call_id": "c", "tool": "t", "outcome": "paused"}),
        (TextToolCall, {"call_id": "c", "tool": "t", "outcome": "ok"}),  # ended: its time
        (TextToolCall, {"call_id": "c", "tool": "t", "outcome": "running", "ms": 5.0}),
        (TextToolCall, {"call_id": "", "tool": "t", "outcome": "running"}),
        (BlockedClause, {"text": "x", "language": "xx"}),
        (BlockedClause, {"text": "x", "language": "en", "reason": "id"}),
    ],
)
def test_a_turns_data_refuses_a_wrong_value(model: type[Any], values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)
