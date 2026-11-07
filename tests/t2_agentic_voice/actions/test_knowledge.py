"""The knowledge tool (actions/knowledge.py; the design's 6.3): one search per call, in the
reply's language and as the call's caller, at most `limit` passages (the k); each passage's
whole text to the talker, cut at a line (else a word) near `passage_chars`; the top passage with
steps as the card, its steps cut to a card's 50; every passage's text as the guard's evidence.
With `FakeKnowledgeBase`; every passage is written for the test."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from t2_agentic_voice.actions.knowledge import MORE, NAME, PASSAGE_CHARS, knowledge_tool
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


def _search(
    kb: FakeKnowledgeBase, query: str = "نسيت كلمة السر", *, limit: int = 5, **given: Any
) -> ToolResult:
    made = knowledge_tool(kb, description="Search the help articles.", limit=limit, **given)
    request = ToolCallRequest(id="c-1", name=NAME, arguments=json.dumps({"query": query}))
    return asyncio.run(ToolRunner([made]).run(request, CTX, clock=FakeClock()))


def _text(text: str, **given: Any) -> str:
    """What the talker reads of a passage of `text`."""
    found = ARCHIVE.model_copy(update={"text": text})
    return str(_data(_search(FakeKnowledgeBase([found]), **given))["passages"][0]["text"])


def test_one_search_in_the_reply_language_as_the_caller_at_most_the_limit() -> None:
    kb = FakeKnowledgeBase([RESET, ARCHIVE])
    result = _search(kb, limit=1)
    assert kb.searches == [
        KnowledgeSearch(query="نسيت كلمة السر", language="ar-SA", caller=CALLER, limit=1)
    ]
    assert [p["id"] for p in _data(result)["passages"]] == ["made-up-001"]


def test_the_talker_gets_each_passage_whole_and_the_steps_the_card_shows() -> None:
    result = _search(FakeKnowledgeBase([RESET, ARCHIVE]))
    assert result.data == {
        "passages": [
            {"id": "made-up-001", "title": "Reset a password", "text": RESET.text},
            {"id": "made-up-002", "title": "Archive a letter", "text": "Use the Archive menu."},
        ],
        "shown_on_screen": {
            "title": "Reset a password",
            "steps": ["Open the portal", "Choose Forgot password", "Enter code 8841"],
        },
    }
    assert result.ok


def test_a_passage_keeps_its_lines_each_with_its_spaces_collapsed() -> None:
    assert _text("  Open   the portal. \n\n\t Choose Forgot password.\r\n") == (
        "Open the portal.\nChoose Forgot password."
    )


def test_a_long_passage_is_cut_at_the_last_line_that_fits_near_passage_chars() -> None:
    lines = [f"Line {n:02d} of the made-up passage." for n in range(1, 41)]  # 31 characters
    text = _text("\n".join(lines), passage_chars=100)
    assert text == "\n".join(lines[:3]) + MORE  # 95 characters: a fourth line passes 100


def test_a_line_far_from_passage_chars_gives_way_to_the_last_word_that_fits() -> None:
    first, second = "A short line.", " ".join(["word"] * 60)
    text = _text(f"{first}\n{second}", passage_chars=100)
    kept = text.removesuffix(MORE)
    assert text.endswith(MORE) and 90 < len(kept) <= 100
    assert kept.splitlines() == [first, " ".join(["word"] * len(kept.split()[3:]))]


def test_a_passage_with_no_space_near_passage_chars_is_cut_at_it() -> None:
    assert _text("x" * 300, passage_chars=100) == "x" * 100 + MORE


def test_passage_chars_is_1500_by_default() -> None:
    assert PASSAGE_CHARS == 1500
    whole = "\n".join(["w" * 99] * 15)  # 1,499 characters
    assert _text(whole) == whole
    assert _text(whole + "\nOne line more.") == whole + MORE


def test_the_top_passage_with_steps_is_the_card_and_every_passage_is_evidence() -> None:
    result = _search(FakeKnowledgeBase([RESET, ARCHIVE]))
    assert result.card == Card(
        title="Reset a password",
        steps=("Open the portal", "Choose Forgot password", "Enter code 8841"),
        source="Made-up guide",
    )
    assert RESET.text in result.evidence and ARCHIVE.text in result.evidence
    assert "Enter code 8841" in result.evidence


def test_a_cut_passage_is_still_whole_in_the_evidence() -> None:
    long = ARCHIVE.model_copy(update={"text": "Open the menu. " * 20 + "The code 4417 ends it."})
    result = _search(FakeKnowledgeBase([long]), passage_chars=50)
    assert "4417" not in _data(result)["passages"][0]["text"]
    assert long.text in result.evidence


def test_a_top_passage_with_no_steps_gives_no_card() -> None:
    result = _search(FakeKnowledgeBase([ARCHIVE, RESET]))
    assert result.card is None and "shown_on_screen" not in _data(result)


def test_a_card_holds_at_most_fifty_steps() -> None:
    many = RESET.model_copy(update={"steps": tuple(f"Step {n}" for n in range(1, 61))})
    card = _search(FakeKnowledgeBase([many])).card
    assert card is not None and len(card.steps) == 50 and card.steps[-1] == "Step 50"


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


@pytest.mark.parametrize("field", ["limit", "passage_chars"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_a_limit_or_passage_chars_under_one_is_a_configuration_error(
    field: str, value: Any
) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as raised:
        knowledge_tool(FakeKnowledgeBase(), description="Search.", **{field: value})
    assert raised.value.details == {"field": field}
    assert f"{field}=" in raised.value.message


def test_a_top_passage_whose_title_says_nothing_gives_no_card() -> None:
    blank = RESET.model_copy(update={"title": "   ", "source": "  "})
    result = _search(FakeKnowledgeBase([blank]))
    assert result.card is None and result.ok
