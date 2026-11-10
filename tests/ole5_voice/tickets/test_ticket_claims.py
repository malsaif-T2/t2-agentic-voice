"""Rule A on Ole5's ticket calls end to end (plan 007's whole-code review; docs/SECURITY.md,
invariant 2), through `TextCall` on the served talker, as test_ticket_calls.py runs them
(call_support.py):

- A caller with no ticket asks its status, of all their tickets or by digits that match none:
  the status finds nothing and holds no ticket, so it backs no claim. A claim the model then
  writes with no ticket made is blocked as it is with no status at all, in both languages, and
  `call.violations` stays clean.
- A claim written in the call's other language is blocked too, as plan 006's run K saw the model
  drift into a passage's language: a passage's made-up ticket number said as the caller's, in
  Arabic in an English call and in English in an Arabic one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from t2_agentic_voice.evals import ScriptedLLM
from t2_agentic_voice.ports import Passage

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    blocks,
    model,
    ole5,
    said,
    text_call,
)
from tests.ole5_voice.tickets.ticket_support import run

# The caller asking how their ticket stands, then for one to be opened, and the model's claim
# that it opened one, though it called no action: «tamma fatH at-tadhkira», the ticket was
# opened, and the support team will call you.
STATUS: Final = {"ar-SA": "وش صار على تذكرتي؟", "en": "What is the status of my ticket?"}
OPEN: Final = {
    "ar-SA": "طيب افتح لي تذكرة عن صفحة التقارير",
    "en": "Then open one for my reports page",
}
OPENED: Final = {
    "ar-SA": "تم فتح التذكرة وفريق الدعم بيتواصل معك.",
    "en": "I've opened a ticket for your reports page, the team will call you.",
}
# Digits of a ticket number the caller says, which none of theirs ends in, and the caller asking
# by them: «tadhkirti illi tintihi bil-arqaam», my ticket ending in the digits.
DIGITS: Final = "1234"
ENDING: Final = {
    "ar-SA": f"وش صار على تذكرتي اللي تنتهي بالأرقام {DIGITS}؟",
    "en": f"What is the status of my ticket ending {DIGITS}?",
}
# A guide's passage holding a made-up ticket number, the caller asking for theirs, and the model
# saying that number is theirs in a claim: I opened you a ticket, its number is ...
NUMBER: Final = "2026102282004417"
FAKE_NUMBER: Final = Passage(
    id="made-up-follow-up",
    title="متابعة بلاغ",
    text=f"لمتابعة البلاغ استخدم رقم التذكرة {NUMBER}، ويرد عليك فريق الدعم خلال يوم عمل.",
    score=0.7,
)
FOLLOW_UP: Final = {
    "ar-SA": "وش رقم البلاغ اللي رفعته عن المرفقات؟",
    "en": "What is the number of my ticket about attachments?",
}
AS_YOURS: Final = {
    "ar-SA": f"فتحت لك تذكرة رقمها {NUMBER}.",
    "en": f"I've opened your ticket, its number is {NUMBER}.",
}


@pytest.mark.parametrize("digits", [None, DIGITS], ids=["all", "no_match"])
@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_a_status_that_found_no_ticket_backs_no_claim(
    tmp_path: Path, tag: Tag, digits: str | None
) -> None:
    agent, tickets = ole5(tmp_path)
    asked = STATUS[tag] if digits is None else ENDING[tag]
    looked = {} if digits is None else {"number": digits}
    llm = model(
        Answer(asked, ScriptedLLM.call_tool("ticket_status", **looked)),
        Answer(asked, ScriptedLLM.reply("ok."), "ticket_status"),
        Answer(OPEN[tag], ScriptedLLM.reply(OPENED[tag])),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            status = await call.user(asked)
            await call.advance(SETTLE_S)
            status.expect.tool_call("ticket_status", **looked)
            opened = await call.user(OPEN[tag])
            await call.advance(SETTLE_S)
            assert [blocked.unsupported for blocked in opened.blocked] == [()]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert OPENED[tag] not in said(call)
            assert call.violations == ()
        assert tickets.listed() == ()

    run(scene())


@pytest.mark.parametrize(("tag", "written"), [("en", "ar-SA"), ("ar-SA", "en")])
def test_a_claim_in_the_calls_other_language_is_blocked(
    tmp_path: Path, tag: Tag, written: Tag
) -> None:
    agent, tickets = ole5(tmp_path, [FAKE_NUMBER])
    llm = model(
        Answer(FOLLOW_UP[tag], ScriptedLLM.call_tool("search_knowledge", query=FOLLOW_UP[tag])),
        Answer(FOLLOW_UP[tag], ScriptedLLM.reply(AS_YOURS[written]), "search_knowledge"),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(FOLLOW_UP[tag])
            await call.advance(SETTLE_S)
            asked.expect.tool_call("search_knowledge")
            # One clause blocked, the rest of the reply dropped with it: an Arabic reply's
            # clauses end at a comma too, so the English claim may be cut before its number.
            assert len(asked.blocked) == 1
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert NUMBER not in said(call)
            assert call.violations == ()
        assert tickets.listed() == ()

    run(scene())
