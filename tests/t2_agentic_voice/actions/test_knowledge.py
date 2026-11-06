"""The knowledge tool (actions/knowledge.py; the design's 6.3): one search per call, in the
reply's language and as the call's caller, at most `limit` passages; short summaries to the
talker; the top passage with steps as the card, its steps cut to a card's 50; every passage's
text as the guard's evidence. With `FakeKnowledgeBase`; every passage is written for the test."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from t2_agentic_voice.actions.knowledge import NAME, SUMMARY_CHARS, knowledge_tool
from t2_agentic_voice.actions.runner import FAILED, ToolRunner
from t2_agentic_voice.actions.tools import CallContext, ToolResult
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase, KnowledgeSearch

from tests.t2_agentic_voice.fakes import FakeClock

CALLER = Caller(subject="made-up-subject")
CTX = CallContext(caller=CALLER, call_id="call-1", language="ar-SA")
RESET = Passage(
    id="made-up-001",
    title="Reset a password",
    text="Open the portal.\nChoose Forgot password.\nThe code 8841 expires in 10 minutes.\nMore.",
    steps=("Open the portal", " ", "Choose Forgot password", "Enter code 8841"),
    score=0.71,
    source="Made-up guide",
)
ARCHIVE = Passage(
    id="made-up-002", title="Archive a letter", text="Use the Archive menu.", score=0.5
)


def _data(result: ToolResult) -> Any:
    """A result's data, as the JSON it is, for a test to index."""
    return json.loads(json.dumps(result.data))


def _search(kb: FakeKnowledgeBase, query: str = "نسيت كلمة السر", *, limit: int = 5) -> ToolResult:
    runner = ToolRunner([knowledge_tool(kb, description="Search the help articles.", limit=limit)])
    request = ToolCallRequest(id="c-1", name=NAME, arguments=json.dumps({"query": query}))
    return asyncio.run(runner.run(request, CTX, clock=FakeClock()))


def test_one_search_in_the_reply_language_as_the_caller_at_most_the_limit() -> None:
    kb = FakeKnowledgeBase([RESET, ARCHIVE])
    result = _search(kb, limit=1)
    assert kb.searches == [
        KnowledgeSearch(query="نسيت كلمة السر", language="ar-SA", caller=CALLER, limit=1)
    ]
    assert [p["id"] for p in _data(result)["passages"]] == ["made-up-001"]


def test_the_talker_gets_short_summaries_and_the_steps_the_card_shows() -> None:
    result = _search(FakeKnowledgeBase([RESET, ARCHIVE]))
    assert result.data == {
        "passages": [
            {
                "id": "made-up-001",
                "title": "Reset a password",
                "summary": (
                    "Open the portal. Choose Forgot password. The code 8841 expires in 10 minutes."
                ),
            },
            {"id": "made-up-002", "title": "Archive a letter", "summary": "Use the Archive menu."},
        ],
        "shown_on_screen": {
            "title": "Reset a password",
            "steps": ["Open the portal", "Choose Forgot password", "Enter code 8841"],
        },
    }
    assert result.ok


def test_the_top_passage_with_steps_is_the_card_and_every_passage_is_evidence() -> None:
    result = _search(FakeKnowledgeBase([RESET, ARCHIVE]))
    assert result.card == Card(
        title="Reset a password",
        steps=("Open the portal", "Choose Forgot password", "Enter code 8841"),
        source="Made-up guide",
    )
    assert RESET.text in result.evidence and ARCHIVE.text in result.evidence
    assert "Enter code 8841" in result.evidence


def test_a_top_passage_with_no_steps_gives_no_card() -> None:
    result = _search(FakeKnowledgeBase([ARCHIVE, RESET]))
    assert result.card is None and "shown_on_screen" not in _data(result)


def test_a_card_holds_at_most_fifty_steps() -> None:
    many = RESET.model_copy(update={"steps": tuple(f"Step {n}" for n in range(1, 61))})
    card = _search(FakeKnowledgeBase([many])).card
    assert card is not None and len(card.steps) == 50 and card.steps[-1] == "Step 50"


def test_a_long_text_is_summarized_at_a_word() -> None:
    long = ARCHIVE.model_copy(update={"text": "word " * 200})
    summary = _data(_search(FakeKnowledgeBase([long])))["passages"][0]["summary"]
    assert summary.endswith(" ...") and len(summary) <= SUMMARY_CHARS + 4
    assert summary.removesuffix(" ...").split() == ["word"] * len(summary.split()[:-1])


def test_nothing_found_is_an_empty_list() -> None:
    result = _search(FakeKnowledgeBase())
    assert result == ToolResult(data={"passages": []})


def test_what_is_no_passage_is_the_tools_failure() -> None:
    class Broken(FakeKnowledgeBase):
        async def search(self, query: str, **_: Any) -> list[Passage]:
            return [{"id": "x"}]  # type: ignore[list-item]

    assert _search(Broken()) == ToolResult(data={"error": FAILED}, ok=False)


def test_the_query_is_the_only_parameter_the_talker_sees() -> None:
    made = knowledge_tool(FakeKnowledgeBase(), description="Search.", progress="searching")
    assert (made.name, made.progress) == (NAME, "searching")
    schema: Any = made.tool_schema().parameters
    assert list(schema["properties"]) == ["query"]
    assert schema["required"] == ["query"]


@pytest.mark.parametrize("limit", [0, -1, True])
def test_a_limit_under_one_is_a_configuration_error(limit: int) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        knowledge_tool(FakeKnowledgeBase(), description="Search.", limit=limit)
    assert raised.value.details == {"field": "limit"}
