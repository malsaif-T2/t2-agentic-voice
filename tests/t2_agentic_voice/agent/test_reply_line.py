"""The reply's language after a tool result (agent/turn.py, agent/prompt.py; plan 006, run K's
first dev round): every request that follows a tool exchange of the turn ends with a short system
line naming the reply's language, so the last thing the model reads before it writes is the
language to write in, whatever language the results are in. The round's English questions were
answered in Arabic after seven Arabic passages, the prompt's language section said English. The
first request of a turn is as it was, and a turn with no tool sends no such line. Every passage
is written for the test."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.agent.prompt import NO_MORE_TOOLS
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatRequest
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

from tests.t2_agentic_voice.agent.chat_support import reply, talker

# A made-up passage in Arabic, as the knowledge base an Arabic agent searches holds.
ARABIC = Passage(
    id="made-up-ar-001",
    title="استعادة الرمز",
    text="افتح البوابة ثم اختر الرمز.",
    score=0.7,
)
ENGLISH_TURN = TalkerTurn(turn_id=1, words="How do I get my code back?", language="en")
# abi arajji' arramz, I want my code back (Saudi): abi, a Saudi word, then two of MSA's
SAUDI_TURN = TalkerTurn(
    turn_id=1,
    words="ابي ارجع الرمز",
    language="ar",
)
WHATEVER = "whatever language the tool results are in"


def _search() -> Any:
    return knowledge_tool(FakeKnowledgeBase([ARABIC]), description="Search the help articles.")


def _searched_then_said(*, times: int = 1) -> ScriptedLLM:
    """A model that searches `times` times, then answers."""
    script = [ScriptedLLM.call_tool(NAME, query="code") for _ in range(times)]
    return ScriptedLLM([*script, ScriptedLLM.reply("Open the portal.")])


def _lines(request: ChatRequest) -> list[ChatMessage]:
    """The request's system messages that name the reply's language after a tool result."""
    return [m for m in request.messages[1:] if m.role == "system" and WHATEVER in m.content]


def _asked(turn: TalkerTurn, call: LanguageTag, llm: Any) -> list[ChatRequest]:
    reply(talker(llm, _search(), language=call), turn)
    return list(llm.requests)


def test_an_english_turn_of_an_arabic_call_ends_the_request_after_its_result_in_english() -> None:
    first, second = _asked(ENGLISH_TURN, "ar-SA", _searched_then_said())
    assert [m.role for m in second.messages[-3:]] == ["assistant", "tool", "system"]
    last = second.messages[-1]
    assert last.content.startswith("Reply in English, the caller's language,")
    assert WHATEVER in last.content
    assert first.messages[-1] == ChatMessage.user(ENGLISH_TURN.words)  # the first as it was
    assert _lines(first) == []


def test_an_arabic_turn_ends_the_request_after_its_result_in_arabic() -> None:
    _, second = _asked(SAUDI_TURN, "ar-SA", _searched_then_said())
    last = second.messages[-1]
    assert last.role == "system"
    assert last.content.startswith("Reply in Arabic, in the Saudi dialect")
    assert WHATEVER in last.content
    english_call = _asked(SAUDI_TURN, "en", _searched_then_said())  # its tag the turn's own
    assert english_call[1].messages[-1] == last


def test_a_turn_with_no_tool_sends_no_such_line() -> None:
    def answer(request: ChatRequest) -> Iterable[ScriptStep]:
        return ScriptedLLM.reply("Hello, how can I help?")

    llm = FunctionLLM(answer)
    [only] = _asked(ENGLISH_TURN, "ar-SA", llm)
    assert only.messages[-1] == ChatMessage.user(ENGLISH_TURN.words)
    assert _lines(only) == []


def test_each_request_after_a_result_ends_with_one_line_never_two() -> None:
    """The third request, after two exchanges, ends with the line once: it is the request's,
    never kept in the turn's messages."""
    first, second, third = _asked(ENGLISH_TURN, "ar-SA", _searched_then_said(times=2))
    assert [len(_lines(r)) for r in (first, second, third)] == [0, 1, 1]
    assert third.messages[-1].content == f"{NO_MORE_TOOLS} {second.messages[-1].content}"
    assert [m.role for m in third.messages[-2:]] == ["system", "system"]
    assert all(m.role != "tool" and not m.tool_calls for m in third.messages)  # no call to copy
    assert sum(m.content.startswith('<data tool="') for m in third.messages) == 2  # results kept


def test_the_next_turns_first_request_holds_no_line_from_the_last_turns_tools() -> None:
    """The kept exchange of a past turn reaches the next turn's first request (its tool result
    among the history), and no line comes with it: the line is for a result of this turn."""
    llm = ScriptedLLM(
        [
            ScriptedLLM.call_tool(NAME, query="code"),
            ScriptedLLM.reply("Open the portal."),
            ScriptedLLM.reply("Then choose the code."),
        ]
    )
    chat = talker(llm, _search(), language="ar-SA")
    reply(chat, ENGLISH_TURN)
    heard = Conversation(turns=(PastTurn(turn_id=1, words=ENGLISH_TURN.words, fate="answered"),))
    reply(chat, TalkerTurn(turn_id=2, words="And then?", language="en", conversation=heard))
    nexts = llm.requests[2]
    assert any(m.role == "tool" for m in nexts.messages)  # the past turn's result is there
    assert _lines(nexts) == []
    assert nexts.messages[-1] == ChatMessage.user("And then?")
