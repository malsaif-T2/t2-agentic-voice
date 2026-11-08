"""Ole5's talker over a text call, an uncertain overlap decided by the model (D-069; plan 006, Q28,
run S's s09): the two words «أبغى موظف» (I want an employee) said over a reply are answered when
the model says stop, as what ships through `talker_agent` (the server, `TextCall`, `AudioCall`);
the echo does not ask; and a single word over a reply still keeps the rule."""

from __future__ import annotations

import asyncio

from ole5_voice.agent import ECHO_AGENT, talker_agent
from t2_agentic_voice.evals import ScriptedLLM, TextCall, TextTurn

LONG = (
    "تقدر تسوي هذا من صفحة الاجازات في اوله فايف، تدخل على الطلبات وبعدين تختار طلب جديد وتعبيه "
    "ثم ترسله للمدير عشان يوافق عليه وهذا كل شي."
)
REQUEST = "أبغى موظف"  # abgha muwazzaf: I want an employee
ANSWER = "ما أقدر أوصلك بموظف الحين."


def test_the_talker_asks_and_the_echo_does_not() -> None:
    assert talker_agent(None).ask_on_uncertain_overlaps
    assert not ECHO_AGENT.ask_on_uncertain_overlaps


async def _scene(llm: ScriptedLLM, words: str) -> TextTurn:
    async with TextCall(talker_agent(None), llm=llm) as call:
        await call.user("كيف أطلب اجازة؟")
        said_over = await call.user(words, during="agent_speaking")
        await call.advance(5.0)
        return said_over


def test_a_short_request_over_a_reply_is_answered_when_the_model_says_stop() -> None:
    llm = ScriptedLLM(
        [ScriptedLLM.reply(LONG), ScriptedLLM.reply("stop"), ScriptedLLM.reply(ANSWER)]
    )
    turn = asyncio.run(_scene(llm, REQUEST))
    turn.expect.said(contains="موظف")
    instruction = llm.requests[1].messages[0].content
    assert "Answer with one word only" in instruction
    assert REQUEST in llm.requests[1].messages[1].content
    assert llm.requests[1].reasoning_effort == "low"
    assert len(llm.requests) == 3  # the first reply, the model's word, the answer


def test_a_single_word_over_a_reply_keeps_the_rule_and_asks_nothing() -> None:
    llm = ScriptedLLM([ScriptedLLM.reply(LONG)])
    asyncio.run(_scene(llm, "موظف"))
    assert len(llm.requests) == 1
