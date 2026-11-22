"""The reply's language named at the end of every request (`llm.reply_line_always`; agent/
turn_request.py, agent/prompt.py): the owner's calls of 2026-11-22 had English small talk in an
Arabic call, which calls no tool, written in Arabic and read by the English voice; 15 plays of
5 switch dialogues had 8 of 30 switched turns in the wrong language without the line and 0 of
30 with it. On, a request with no tool result before it ends with the language alone, in the
turn's language and register; after a tool the line is as it was, once; the last request's
opens with `NO_MORE_TOOLS`. Off (the default, GP-18), every request is as it was, message for
message. Every passage and sentence is written for the test."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.agent.prompt import (
    LANGUAGE_LINES,
    MSA_LANGUAGE_LINE,
    NO_MORE_TOOLS,
    REPLY_LINES,
)
from t2_agentic_voice.agent.turn_request import request_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import WordSettings
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatRequest
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.evals import FunctionLLM, ScriptedLLM, ScriptStep
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase

from tests.t2_agentic_voice.agent.chat_support import reply, talker

PASSAGE = Passage(id="made-up-ar-003", title="الرمز", text="افتح البوابة ثم اختر الرمز.", score=0.7)
ENGLISH_TURN = TalkerTurn(turn_id=1, words="How is it going with you?", language="ar")
SAUDI = "ابي ارجع الرمز"  # abi arajji' arramz, I want my code back: abi is Saudi
MSA = "كيف أطبع الرسالة من النظام؟"  # kayfa atba'u, how do I print: no dialect form
ON = VoiceSettings(env="test", llm=LlmSettings(reply_line_always=True))


def _search() -> Any:
    return knowledge_tool(FakeKnowledgeBase([PASSAGE]), description="Search the help articles.")


def _chatted(llm: Any, *turns: TalkerTurn, call: LanguageTag, settings: VoiceSettings) -> Any:
    chat = talker(llm, _search(), language=call, settings=settings)
    for turn in turns:
        reply(chat, turn)
    return llm


def _small_talk() -> FunctionLLM:
    def answer(request: ChatRequest) -> Iterable[ScriptStep]:
        return ScriptedLLM.reply("Fine, thanks.")

    return FunctionLLM(answer)


def _named(request: ChatRequest) -> list[str]:
    """The request's system lines, past its prompt, that name the reply's language."""
    return [
        m.content for m in request.messages[1:] if m.role == "system" and "Reply in" in m.content
    ]


@pytest.mark.parametrize(
    ("words", "call", "words_settings", "line"),
    [
        (ENGLISH_TURN.words, "ar-SA", WordSettings(), LANGUAGE_LINES["en"]),
        (SAUDI, "ar-SA", WordSettings(), LANGUAGE_LINES["ar-SA"]),
        (MSA, "ar-SA", WordSettings(), MSA_LANGUAGE_LINE),
        (MSA, "ar-SA", WordSettings(fixed_register="saudi"), LANGUAGE_LINES["ar-SA"]),
        (SAUDI, "ar", WordSettings(), LANGUAGE_LINES["ar"]),
    ],
    ids=["en", "ar-SA-saudi", "ar-SA-msa", "ar-SA-held-saudi", "ar"],
)
def test_a_turn_with_no_tool_ends_its_request_with_its_language_and_register(
    words: str, call: LanguageTag, words_settings: WordSettings, line: str
) -> None:
    settings = ON.model_copy(update={"words": words_settings})
    turn = TalkerTurn(turn_id=1, words=words, language="ar")
    [only] = _chatted(_small_talk(), turn, call=call, settings=settings).requests
    assert only.messages[-2:] == (ChatMessage.user(words), ChatMessage.system(line))
    assert _named(only) == [line]  # the language alone, never the clause on results


def test_the_wording_is_the_replays() -> None:
    assert LANGUAGE_LINES == {
        "ar-SA": "Reply in Arabic, in the Saudi dialect, the caller's language.",
        "ar": "Reply in Arabic, the caller's language.",
        "en": "Reply in English, the caller's language.",
    }
    assert MSA_LANGUAGE_LINE == "Reply in Modern Standard Arabic, the caller's register."
    whatever = ", whatever language the tool results are in."
    assert REPLY_LINES["en"] == f"Reply in English, the caller's language{whatever}"


def test_after_a_tool_the_line_is_as_it_was_once_and_the_last_opens_with_no_more_tools() -> None:
    script = [ScriptedLLM.call_tool(NAME, query="code") for _ in range(2)]
    llm = ScriptedLLM([*script, ScriptedLLM.reply("Open the portal.")])
    first, second, third = _chatted(llm, ENGLISH_TURN, call="ar-SA", settings=ON).requests
    assert _named(first) == [LANGUAGE_LINES["en"]]
    assert _named(second) == [REPLY_LINES["en"]]  # the first's line never kept
    assert _named(third) == [f"{NO_MORE_TOOLS} {REPLY_LINES['en']}"]
    assert [m.role for m in second.messages[-3:]] == ["assistant", "tool", "system"]


def test_a_last_request_with_no_result_before_it_opens_with_no_more_tools() -> None:
    messages = [ChatMessage.system("Made-up prompt."), ChatMessage.user("Thanks, bye.")]
    llm = LlmSettings(reply_line_always=True, vary_first_line=False)
    last = request_of(llm, messages, (), after_tools=False, language="en", register="saudi")
    assert last.messages[-1] == ChatMessage.system(f"{NO_MORE_TOOLS} {LANGUAGE_LINES['en']}")
    off = request_of(
        LlmSettings(), messages, (), after_tools=False, language="en", register="saudi"
    )
    assert off.messages[1:] == (ChatMessage.user("Thanks, bye."),)


def _dialogue(settings: VoiceSettings) -> list[ChatRequest]:
    """An English turn of an Arabic call answered after a search, then one answered at once."""
    llm = ScriptedLLM(
        [
            ScriptedLLM.call_tool(NAME, query="code"),
            ScriptedLLM.reply("Open the portal."),
            ScriptedLLM.reply("Then choose the code."),
        ]
    )
    heard = Conversation(turns=(PastTurn(turn_id=1, words=ENGLISH_TURN.words, fate="answered"),))
    nexts = TalkerTurn(turn_id=2, words="And then what?", language="ar", conversation=heard)
    return list(_chatted(llm, ENGLISH_TURN, nexts, call="ar-SA", settings=settings).requests)


def _bare(request: ChatRequest) -> ChatRequest:
    """`request` with its first line, new on every request, taken out."""
    prompt = ChatMessage.system(request.messages[0].content.split("\n", 1)[1])
    return request.model_copy(update={"messages": (prompt, *request.messages[1:])})


def test_off_every_request_is_as_it_was_and_on_adds_only_the_line() -> None:
    off = [_bare(r) for r in _dialogue(VoiceSettings(env="test"))]
    assert [len(_named(r)) for r in off] == [0, 1, 0]  # only after the result, as before
    assert off[0].messages[-1] == ChatMessage.user(ENGLISH_TURN.words)
    assert off[2].messages[-1] == ChatMessage.user("And then what?")
    on = [_bare(r) for r in _dialogue(ON)]
    line = ChatMessage.system(LANGUAGE_LINES["en"])
    added = [(*off[0].messages, line), off[1].messages, (*off[2].messages, line)]
    assert [r.messages for r in on] == added
    assert [r.model_copy(update={"messages": ()}) for r in on] == [
        r.model_copy(update={"messages": ()}) for r in off
    ]
