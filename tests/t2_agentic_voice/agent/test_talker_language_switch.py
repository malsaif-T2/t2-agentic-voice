"""The talker's reply after its `switch_language` tool (agent/turn.py, actions/language_tool.py;
D-038's amendment): the rest of the turn is in the language the caller asked for (the next
request's system prompt and its closing line, every later clause's tag), and `LanguageMoved`
tells the session, once, after the tool's result; what was said before the call keeps its
language; a switch to the language the reply is in already, or one that failed, moves nothing.
Every line is written for the test."""

from __future__ import annotations

from t2_agentic_voice.actions.language_tool import NAME, language_tool
from t2_agentic_voice.agent.prompt import REPLY_LINES
from t2_agentic_voice.agent.talker import ChatTalker, LanguageMoved, SpokenClause
from t2_agentic_voice.core.conversation import TalkerTurn

from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    INSTRUCTIONS,
    SAUDI,
    FakeChat,
    agent,
    call,
    calls,
    kinds,
    reply,
    said,
    talker,
)

TWO = (SAUDI, ENGLISH)
TURN = TalkerTurn(turn_id=1, words="ممكن نكمل بلغة ثانية؟", language="ar-SA")


def _talker(model: FakeChat) -> ChatTalker:
    return talker(model, language_tool(TWO), language="ar-SA", declared=agent(languages=TWO))


def test_after_the_switch_the_rest_of_the_turn_is_in_the_new_language() -> None:
    model = FakeChat(
        calls(call(NAME, language="en"), before="أكيد. "),
        said("Sure, how can I help?"),
    )
    events = reply(_talker(model), TURN)
    assert kinds(events).count("LanguageMoved") == 1
    moved = kinds(events).index("LanguageMoved")
    assert kinds(events)[moved - 1] == "ToolEnded"
    assert [e for e in events if isinstance(e, LanguageMoved)] == [LanguageMoved(language="en")]
    clauses = [(e.text, e.language) for e in events if isinstance(e, SpokenClause)]
    assert clauses == [("أكيد.", "ar-SA"), ("Sure, how can I help?", "en")]
    first, second = model.requests
    assert INSTRUCTIONS["ar-SA"] in first.messages[0].content
    assert INSTRUCTIONS["en"] in second.messages[0].content
    assert INSTRUCTIONS["ar-SA"] not in second.messages[0].content
    assert second.messages[-1].content.endswith(REPLY_LINES["en"])


def test_a_switch_to_the_replys_own_language_moves_nothing() -> None:
    model = FakeChat(calls(call(NAME, language="ar")), said("تمام، وش تبي؟"))
    events = reply(_talker(model), TURN)
    assert "LanguageMoved" not in kinds(events)
    assert {e.language for e in events if isinstance(e, SpokenClause)} == {"ar-SA"}


def test_a_switch_the_tool_refused_moves_nothing() -> None:
    model = FakeChat(calls(call(NAME, language="fr")), said("ما أقدر، أكمل معك بالعربي."))
    events = reply(_talker(model), TURN)
    assert "LanguageMoved" not in kinds(events)
    assert {e.language for e in events if isinstance(e, SpokenClause)} == {"ar-SA"}
    assert INSTRUCTIONS["ar-SA"] in model.requests[1].messages[0].content
