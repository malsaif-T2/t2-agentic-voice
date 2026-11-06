"""The seam between runs K and S and `TextCall` (talker_call.py), on a fake call with
`TextCall`'s signature: a variant said once in a call held on the system clock, a scenario's
turns each said when it says, and each turn's data read into what a run keeps."""

from __future__ import annotations

import asyncio
import inspect

from ole5_voice.evals.scenarios import ScriptTurn
from ole5_voice.evals.talker_call import ask, heard, play
from t2_agentic_voice import Card, LlmSettings, VoiceSettings
from t2_agentic_voice.evals import BlockedClause, HeardClause, TextCall, TextToolCall
from t2_agentic_voice.ports import Usage

from tests.ole5_voice.evals.talker_fakes import (
    TOOL,
    Calls,
    FakeChat,
    FakeKnowledgeBase,
    FakeTurn,
    Scripted,
    agent,
)

SETTINGS = VoiceSettings(env="test", llm=LlmSettings(model="openai/gpt-oss-20b"))


def test_a_turns_data_is_read_as_a_run_keeps_it() -> None:
    turn = FakeTurn(
        fate="cut",
        clauses=(
            HeardClause(text="One.", language="ar-SA", fate="played", played_fraction=1.0),
            HeardClause(text="Two.", language="ar-SA", fate="cut", played_fraction=0.5),
            HeardClause(
                text="Wait.", language="ar-SA", fate="played", played_fraction=1.0, phrase=True
            ),
        ),
        tool_calls=(
            TextToolCall(
                call_id="c", tool=TOOL, arguments={"query": "q"}, outcome="cancelled", ms=3.0
            ),
        ),
        cards=(Card(title="T", steps=("a", "b"), source="S"),),
        blocked=(BlockedClause(text="x", language="en", unsupported=("123",)),),
        first_token_s=0.1,
        first_clause_s=0.3,
        model_requests=2,
        usage=Usage(input_tokens=50, output_tokens=7),
    )
    kept = heard(turn)
    assert kept.said == "One. Two." and kept.words == 2 and kept.language == "ar-SA"
    assert kept.tools[0].arguments == {"query": "q"} and kept.tools[0].outcome == "cancelled"
    assert kept.searched(TOOL) and not kept.searched("other")
    assert kept.cards[0].steps == ("a", "b") and kept.blocked == 1
    assert (kept.input_tokens, kept.output_tokens, kept.model_requests) == (50, 7, 2)
    assert "Two. [cut, 50% of it heard]" in kept.heard_text() and "Wait." not in kept.heard_text()


def test_a_variant_is_said_once_in_a_call_on_the_system_clock() -> None:
    calls, chat = Calls(), FakeChat()
    calls.kb = FakeKnowledgeBase()
    calls.script["hello"] = Scripted(violations=1, search=False)
    held = asyncio.run(
        ask(agent(calls.kb), chat, SETTINGS, words="hello", language="ar", call=calls)
    )
    assert calls.said == [("hello", None, None, "ar")]
    assert held.violations == 1 and held.turns[0].said == "A short made-up answer."
    assert chat.requests[0].model == "openai/gpt-oss-20b"


def test_a_scenarios_turns_are_each_said_when_they_say() -> None:
    calls = Calls()
    calls.kb = FakeKnowledgeBase()
    turns = [
        ScriptTurn(says="first", search=True),
        ScriptTurn(says="stop", when="agent_speaking", after_s=1.5, cuts_reply=True),
        ScriptTurn(says="correction", when="tool_running", cancels_search=True),
    ]
    calls.script["stop"] = Scripted(cuts_earlier=True)
    calls.script["correction"] = Scripted(cancels_search=True)
    held = asyncio.run(
        play(agent(calls.kb), FakeChat(), SETTINGS, turns=turns, language="ar-SA", call=calls)
    )
    assert [said[:3] for said in calls.said] == [
        ("first", None, None),
        ("stop", "agent_speaking", None),
        ("correction", None, "tool_running"),
    ]
    assert calls.advanced == [1.5]
    # Every turn is read once the last is answered, so a cut reply reads as it ended.
    assert held.turns[0].fate == "cut" and held.turns[1].tools[0].outcome == "cancelled"


def test_the_default_call_is_the_librarys_text_call() -> None:
    assert inspect.signature(ask).parameters["call"].default is TextCall
    assert inspect.signature(play).parameters["call"].default is TextCall
