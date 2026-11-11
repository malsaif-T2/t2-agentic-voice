"""Ole5's talker says and shows no stray script (D-084), on the library's public API only. In the
owner's demo call of 2026-11-10 (report `0qPpF2-C`), the model wrote «أيقونة "إ重新 كلمة مرور
المستخدم"» where the passage holds «إعادة كلمة مرور المستخدم». Here that answer is scripted
through `TextCall` on the talker the server serves (its search, its tickets, the guard's ticket
claims): the caller hears, and the history the next request reads holds, no Chinese character,
while "Ole5" and a menu path's arrow stay, since Ole5's languages write Arabic and Latin; the
search's query loses its stray character too, and the turn counts what went
(`TextTurn.stray_characters`). With `guard.remove_stray_script` off, the demo's defect is
said, as it was."""

from __future__ import annotations

import asyncio
import unicodedata
from pathlib import Path

from ole5_voice.agent import talker_agent
from ole5_voice.tickets.mock import MockTicketSystem
from ole5_voice.tickets.tools import with_ticket_claims
from t2_agentic_voice import GuardSettings, VoiceSettings
from t2_agentic_voice.evals import FakeKnowledgeBase, ScriptedLLM, TextCall, TextTurn
from t2_agentic_voice.ports import ChatRequest, Passage

# kayf a'eed kalimat muroor mustakhdim fi Ole5: how do I reset a user's password in Ole5?
ASKED = "كيف أعيد كلمة مرور مستخدم في Ole5؟"
THANKS = "شكرا"  # shukran: thank you
# The search's query as the model might write it, a Chinese character in a word.
QUERY = "إعادة重 كلمة مرور المستخدم"
# The demo's answer, with Ole5's name and a menu path: in Ole5, open Users → the user, and
# press the icon "reset the user's password", the model's Chinese word in its place.
ANSWER = 'في Ole5 افتح المستخدمين → المستخدم، واضغط أيقونة "إ重新 كلمة مرور المستخدم".'
SAID = 'في Ole5 افتح المستخدمين → المستخدم، واضغط أيقونة "إ كلمة مرور المستخدم".'
GUIDE = Passage(
    id="guide/users_001",
    title="إعادة كلمة مرور المستخدم",
    text="من المستخدمين اختر المستخدم ثم اضغط أيقونة إعادة كلمة مرور المستخدم.",
    score=1,
)
FINE = "العفو."  # al'afw: you are welcome


def _cjk(text: str) -> list[str]:
    """The characters of `text` the Unicode tables name as CJK, Chinese, Japanese or Korean."""
    return [c for c in text if unicodedata.name(c, "").startswith(("CJK", "HANGUL", "HIRAGANA"))]


def _llm() -> ScriptedLLM:
    return ScriptedLLM(
        [
            ScriptedLLM.call_tools(("search_knowledge", {"query": QUERY})),
            ScriptedLLM.reply(ANSWER),
            ScriptedLLM.reply(FINE),
        ]
    )


def _call(llm: ScriptedLLM, settings: VoiceSettings, folder: Path) -> TextTurn:
    agent = talker_agent(FakeKnowledgeBase([GUIDE]), tickets=MockTicketSystem(folder))

    async def run() -> TextTurn:
        async with TextCall(agent, llm=llm, settings=with_ticket_claims(settings)) as call:
            turn = await call.user(ASKED)
            await call.advance(30.0)
            await call.user(THANKS)
            await call.advance(10.0)
            return turn

    return asyncio.run(run())


def _assistant(request: ChatRequest) -> str:
    """What the agent said and called, as `request` gives it to the model."""
    found = []
    for message in request.messages:
        if message.role == "assistant":
            found.append(message.content)
            found += [call.arguments for call in message.tool_calls]
    return " ".join(found)


def test_the_demos_answer_is_said_and_captioned_with_no_chinese_character(tmp_path: Path) -> None:
    llm = _llm()
    turn = _call(llm, VoiceSettings(env="test"), tmp_path)
    heard = " ".join(clause.text for clause in turn.clauses)
    assert _cjk(heard) == [] and heard == SAID
    assert "Ole5" in heard and "→" in heard
    turn.expect.said(contains='"إ كلمة مرور المستخدم"')
    (search,) = turn.tool_calls
    assert search.arguments == {"query": "إعادة كلمة مرور المستخدم"}
    assert turn.stray_characters == 3  # 重 in the query, 重新 in the answer
    asked_after = llm.requests[-1]  # the next turn's request: the history as the caller heard it
    assert _cjk(_assistant(asked_after)) == [] and SAID in _assistant(asked_after)
    assert GUIDE.text in " ".join(m.content for m in llm.requests[1].messages)  # as written


def test_with_the_setting_off_the_demos_defect_is_said(tmp_path: Path) -> None:
    off = VoiceSettings(env="test", guard=GuardSettings(remove_stray_script=False))
    turn = _call(_llm(), off, tmp_path)
    heard = " ".join(clause.text for clause in turn.clauses)
    assert _cjk(heard) == ["重", "新"] and turn.stray_characters == 0
