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
- A number said as the caller's ticket number («رقم تذكرتك», "your ticket number is") claims any
  of Ole5's actions (the owner's ruling of 2026-11-10; tickets/lines.py's `NUMBER_CLAIMS`): in a
  call with no ticket, a passage's made-up number said so is blocked by rule A, though rule B
  would pass it as a passage's fact, in Saudi Arabic, in MSA, in English and in the call's other
  language; in a call that made a ticket, by either action, its number passes said so, and a
  number no action made is blocked.
- A status backs only a claim that names one of its numbers, or one with no number in a reply
  that already said one (the owner's ruling of 2026-11-10 on TD-144, "Number or same reply"): a
  caller with a ticket from an earlier call asks its status, then for a new ticket, and the
  model's «فتحت لك تذكرة عن صفحة التقارير» (I opened you a ticket about the reports page), with
  no action called, is blocked; a status answer that names the ticket's last four digits, then
  says it was escalated, is said whole, and that claim alone in a later reply is blocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

import pytest
from t2_agentic_voice import VoiceAgent
from t2_agentic_voice.evals import ScriptedLLM, ScriptStep
from t2_agentic_voice.ports import Outbox, Passage
from t2_agentic_voice.stores import MemoryOutbox

from tests.ole5_voice.tickets.call_support import (
    SETTLE_S,
    Answer,
    Tag,
    blocks,
    model,
    ole5,
    said,
    text_call,
    yes_send,
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
# A number said as the caller's ticket number, with no other claim: raqm tadhkirtak, your
# ticket's number; in MSA with huwa (is): raqmu tadhkiratika huwa.
Written = Literal["ar-SA", "msa", "en"]
YOURS: Final[dict[Written, str]] = {
    "ar-SA": "رقم تذكرتك {}.",
    "msa": "رقم تذكرتك هو {}.",
    "en": "Your ticket number is {}.",
}
# The caller's problem and the ticket's draft; the caller asking for a person and the handoff's
# summary; then the caller asking for the number again, and whether it is right.
PROBLEM: Final = {
    "ar-SA": "صفحة التقارير ما تطلع أي بيانات، افتح لي تذكرة.",
    "en": "My reports page shows no data, please open a ticket.",
}
DRAFT: Final = {
    "ar-SA": {"summary": "صفحة التقارير ما تعرض أي بيانات.", "type": "Report"},
    "en": {"summary": "The reports page shows no data.", "type": "Report"},
}
PERSON: Final = {"ar-SA": "أبي أكلم أحد من الدعم.", "en": "I want to talk to someone from support."}
HANDOFF: Final = {
    "ar-SA": {"summary": "يبي يكلم أحد من الدعم عن صفحة التقارير."},
    "en": {"summary": "Wants to talk to support about the reports page."},
}
AGAIN: Final = {"ar-SA": "وش كان الرقم؟", "en": "What was the number again?"}
SURE: Final = {"ar-SA": "متأكد؟", "en": "Are you sure?"}
# A ticket-shaped number no action of the call made.
MADE_UP: Final = "2026111082009999"
# The status of a ticket from an earlier call, by its last four digits: «tadhkirtak illi tintihi
# bil-arqaam ... maftooHa», your ticket ending in the digits ... is open; the model's claim of a
# new ticket with no action called: «fataHt lak tadhkira 'an SafHat at-taqaareer», I opened you
# a ticket about the reports page; a claim with no number: «wa-tamma taS'eed Talabak li-fareeq
# ad-da'm», and your request was escalated to the support team (a default phrase, any action's);
# and the caller asking whether it was: «Sa''adtooha?», did you escalate it?
IS_OPEN: Final = {
    "ar-SA": "تذكرتك اللي تنتهي بالأرقام {} مفتوحة.",
    "en": "Your ticket ending {} is open.",
}
OPENED_NEW: Final = {
    "ar-SA": "فتحت لك تذكرة عن صفحة التقارير.",
    "en": "I've opened a ticket for your reports page.",
}
ESCALATED: Final = {
    "ar-SA": "وتم تصعيد طلبك لفريق الدعم.",
    "en": "It has been escalated to the support team.",
}
WAS_IT: Final = {"ar-SA": "صعدتوها؟", "en": "Was it escalated?"}


async def _made_before(agent: VoiceAgent, tag: Tag, outbox: Outbox) -> None:
    """A ticket made for the caller in an earlier call, its row on `outbox`."""
    llm = model(Answer(PROBLEM[tag], ScriptedLLM.call_tool("create_ticket", **DRAFT[tag])))
    async with text_call(agent, llm, tag, outbox) as first:
        await first.user(PROBLEM[tag])
        sent = await first.user(yes_send(tag))
        await first.advance(SETTLE_S)
        sent.expect.action_completed("create_ticket")


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


@pytest.mark.parametrize(
    ("tag", "written"),
    [("ar-SA", "ar-SA"), ("ar-SA", "msa"), ("en", "en"), ("en", "ar-SA"), ("ar-SA", "en")],
)
def test_a_passages_number_said_as_the_callers_ticket_number_is_blocked(
    tmp_path: Path, tag: Tag, written: Written
) -> None:
    agent, tickets = ole5(tmp_path, [FAKE_NUMBER])
    llm = model(
        Answer(FOLLOW_UP[tag], ScriptedLLM.call_tool("search_knowledge", query=FOLLOW_UP[tag])),
        Answer(
            FOLLOW_UP[tag], ScriptedLLM.reply(YOURS[written].format(NUMBER)), "search_knowledge"
        ),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            asked = await call.user(FOLLOW_UP[tag])
            await call.advance(SETTLE_S)
            asked.expect.tool_call("search_knowledge")
            assert [blocked.unsupported for blocked in asked.blocked] == [(NUMBER,)]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert NUMBER not in said(call)
            assert call.violations == ()
        assert tickets.listed() == ()

    run(scene())


@pytest.mark.parametrize("action", ["create_ticket", "hand_off"])
@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_the_number_of_a_ticket_made_in_the_call_passes_said_as_the_callers(
    tmp_path: Path, tag: Tag, action: str
) -> None:
    """Either action's ticket: the phrase claims any action, so its number passes on that
    action's record; a number no action made, said so, is blocked by rule A, its numbers read
    against the record alone."""
    agent, tickets = ole5(tmp_path)
    asked, draft = (PROBLEM, DRAFT) if action == "create_ticket" else (PERSON, HANDOFF)
    again: list[ScriptStep] = []  # written once the ticket is made, its number known then
    llm = model(
        Answer(asked[tag], ScriptedLLM.call_tool(action, **draft[tag])),
        Answer(AGAIN[tag], again),
        Answer(SURE[tag], ScriptedLLM.reply(YOURS[tag].format(MADE_UP))),
    )

    async def scene() -> None:
        async with text_call(agent, llm, tag) as call:
            await call.user(asked[tag])
            sent = await call.user(yes_send(tag))
            await call.advance(SETTLE_S)
            sent.expect.action_completed(action)
            [made] = tickets.listed()
            again.extend(ScriptedLLM.reply(YOURS[tag].format(made.number)))
            told = await call.user(AGAIN[tag])
            await call.advance(SETTLE_S)
            told.expect.said(contains=YOURS[tag].format(made.number))
            assert told.blocked == ()
            wrong = await call.user(SURE[tag])
            await call.advance(SETTLE_S)
            assert [blocked.unsupported for blocked in wrong.blocked] == [(MADE_UP,)]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert MADE_UP not in said(call)
            assert call.violations == ()

    run(scene())


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_a_status_of_an_older_ticket_backs_no_claim_of_a_new_one(tmp_path: Path, tag: Tag) -> None:
    """The TD-144 scenario, on the served talker's settings: the status lists the caller's
    ticket from an earlier call, so it holds an ID, but the claim names none of its numbers and
    its reply said none; this call's record is empty, so nothing backs it."""
    agent, tickets = ole5(tmp_path)
    outbox = MemoryOutbox()

    async def scene() -> None:
        await _made_before(agent, tag, outbox)
        [made] = tickets.listed()
        told = IS_OPEN[tag].format(made.number[-4:])
        llm = model(
            Answer(STATUS[tag], ScriptedLLM.call_tool("ticket_status")),
            Answer(STATUS[tag], ScriptedLLM.reply(told), "ticket_status"),
            Answer(OPEN[tag], ScriptedLLM.reply(OPENED_NEW[tag])),
        )
        async with text_call(agent, llm, tag, outbox) as call:
            status = await call.user(STATUS[tag])
            await call.advance(SETTLE_S)
            status.expect.tool_call("ticket_status")
            status.expect.said(contains=told)
            assert status.blocked == ()
            opened = await call.user(OPEN[tag])
            await call.advance(SETTLE_S)
            assert [blocked.unsupported for blocked in opened.blocked] == [()]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert OPENED_NEW[tag] not in said(call)
            assert call.violations == ()
        assert [ticket.number for ticket in tickets.listed()] == [made.number]

    run(scene())


@pytest.mark.parametrize("tag", ["ar-SA", "en"])
def test_a_status_answer_that_names_the_last_four_backs_its_claim_in_that_reply(
    tmp_path: Path, tag: Tag
) -> None:
    """The sentence that names the ticket's last four digits, then a claim with no number: said
    whole. The same claim in a later reply, which names no number, is blocked (the accepted
    cost of the ruling)."""
    agent, tickets = ole5(tmp_path)
    outbox = MemoryOutbox()

    async def scene() -> None:
        await _made_before(agent, tag, outbox)
        [made] = tickets.listed()
        told = f"{IS_OPEN[tag].format(made.number[-4:])} {ESCALATED[tag]}"
        llm = model(
            Answer(STATUS[tag], ScriptedLLM.call_tool("ticket_status")),
            Answer(STATUS[tag], ScriptedLLM.reply(told), "ticket_status"),
            Answer(WAS_IT[tag], ScriptedLLM.reply(ESCALATED[tag])),
        )
        async with text_call(agent, llm, tag, outbox) as call:
            status = await call.user(STATUS[tag])
            await call.advance(SETTLE_S)
            status.expect.said(contains=told)
            assert status.blocked == () and blocks(call) == []
            again = await call.user(WAS_IT[tag])
            await call.advance(SETTLE_S)
            assert [blocked.unsupported for blocked in again.blocked] == [()]
            assert [event.reason for event in blocks(call)] == ["unsupported_claim"]
            assert call.violations == ()

    run(scene())
