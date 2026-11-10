"""What backs a claim, and which phrases claim, on the talker's clauses with the real rule A
(agent/speech_guard.py, domain/claims.py; the design's 8.2; docs/SECURITY.md, invariant 2,
GP-08), so no stand-in hides either from the guard:

- A `reports_on` tool's result that succeeded but holds no ID-shaped token, a status that found
  nothing, backs no claim: the claim the model writes after it is blocked as with no status at
  all, while a status that holds a number backs a claim that names it (test_talker_claims.py).
- A status backs only a claim that names one of its numbers, or one with no number in the reply
  whose earlier clause named one (the owner's ruling of 2026-11-10 on TD-144, "Number or same
  reply"): the status of an older request, then "I've opened a request for your reports page"
  with no action called, is blocked; "Your request ending 1234 is open. It has been escalated."
  is said whole; and the second sentence alone, in a later reply, is blocked.
- The claim phrases are every language's the agent's actions and the defaults give, whatever the
  reply's language: a model that writes a claim in its other language is blocked with no record
  and passes with one."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.action_lines import ReadBackPlan

from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CALLER,
    ISSUED,
    confirmed_of,
    context,
    request,
)
from tests.t2_agentic_voice.agent.action_talk_support import Acting, acting
from tests.t2_agentic_voice.agent.chat_support import FakeChat, call, calls, reply, said

ASKED = "Do I have any requests? Open one for my laptop."
ENGLISH = TalkerTurn(turn_id=1, words=ASKED, language="en")
# "abi aftaH Talab 'an al-laptop Haqqi": I want to open a request about my laptop.
SAUDI = TalkerTurn(turn_id=1, words="ابي افتح طلب عن اللابتوب حقي", language="ar-SA")
CLAIM = "I've opened your request for the laptop."
# The claims the model may write in the reply's other language: the action's own English
# phrase, a default English one, the action's own Arabic one («fataHt aT-Talab», I opened the
# request), and a default Arabic one («tamma inshaa' Talabak», your request was created).
OTHER_LANGUAGE = [
    pytest.param(SAUDI, CLAIM, id="own_english_in_arabic"),
    pytest.param(SAUDI, "I have created your request for the laptop.", id="default_english"),
    pytest.param(ENGLISH, "فتحت الطلب حق اللابتوب.", id="own_arabic_in_english"),
    pytest.param(ENGLISH, "تم انشاء طلبك.", id="default_arabic"),
]


@tool(description="Read the caller's made-up requests: none.", reports_on=["open_request"])
async def no_requests() -> dict[str, object]:
    return {"requests": [], "total": 0}


@tool(description="Read the caller's made-up request.", reports_on=["open_request"])
async def one_request() -> dict[str, str]:
    return {"number": ISSUED, "state": "open"}


@tool(description="Read the caller's made-up older requests.", reports_on=["open_request"])
async def older_requests() -> dict[str, object]:
    return {"requests": [{"ends_in": "1234", "state": "open"}], "total": 1}


# The caller asking how their requests stand, then for a new one, then whether it was escalated;
# what the model says of the status, a claim of the new one with no action called, and a claim
# with no number: in English, and in Saudi Arabic («wish Saar 'ala Talabaati?», what became of my
# requests?; «Tayyib iftaH li Talab 'an SafHat at-taqaareer», then open me a request about the
# reports page; «Sa''adtooh?», did you escalate it?).
STATUS_ASKED = {
    "en": TalkerTurn(turn_id=1, words="How are my requests?", language="en"),
    "ar-SA": TalkerTurn(turn_id=1, words="وش صار على طلباتي؟", language="ar-SA"),
}
NEW_ASKED = {
    "en": TalkerTurn(turn_id=2, words="Then open one for my reports page.", language="en"),
    "ar-SA": TalkerTurn(turn_id=2, words="طيب افتح لي طلب عن صفحة التقارير", language="ar-SA"),
}
ESCALATED_ASKED = {
    "en": TalkerTurn(turn_id=2, words="Was it escalated?", language="en"),
    "ar-SA": TalkerTurn(turn_id=2, words="صعدتوه؟", language="ar-SA"),
}
# «Talabak illi yintihi bi-1234 maftooH»: your request ending 1234 is open; «fataHt lak Talab
# 'an SafHat at-taqaareer»: I opened you a request about the reports page; «wa-tamma taS'eed
# Talabak li-fareeq ash-shabakaat»: and your request was escalated to the network team.
IS_OPEN = {"en": "Your request ending 1234 is open.", "ar-SA": "طلبك اللي ينتهي بـ 1234 مفتوح."}
OPENED_NEW = {
    "en": "I've opened a request for your reports page.",
    "ar-SA": "فتحت لك طلب عن صفحة التقارير.",
}
ESCALATED = {
    "en": "It has been escalated to the network team.",
    "ar-SA": "وتم تصعيد طلبك لفريق الشبكات.",
}
TAGS = ["en", "ar-SA"]


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpokenClause)]


def _blocked(events: list[TalkerEvent]) -> list[str]:
    return [e.reason for e in events if isinstance(e, ClauseBlocked)]


def _written(rig: Acting) -> None:
    """The made-up request proposed, confirmed as the yes rule would and written, so the
    call's record holds it."""

    async def run() -> None:
        plan = await rig.runner.propose(request(), context(), clock=rig.clock)
        assert isinstance(plan, ReadBackPlan)
        outcome = await rig.runner.run(
            confirmed_of(plan),
            caller=CALLER,
            call_id=CALL_ID,
            language="en",
            turn_id=0,
            conversation=(),
            clock=rig.clock,
        )
        assert outcome.kind == "done"

    asyncio.run(run())


def test_a_status_that_found_nothing_backs_no_claim() -> None:
    model = FakeChat(calls(call("no_requests")), said(f"You have no requests yet. {CLAIM}"))
    events = reply(acting(model, no_requests).talker, ENGLISH)
    assert _spoken(events) == ["You have no requests yet."]
    assert _blocked(events) == ["unsupported_claim"]


def test_a_status_that_holds_a_number_backs_the_claim_that_names_it() -> None:
    named = f"I've opened your request {ISSUED} for the laptop."
    model = FakeChat(calls(call("one_request")), said(named))
    events = reply(acting(model, one_request).talker, ENGLISH)
    assert _spoken(events) == [named] and _blocked(events) == []


@pytest.mark.parametrize("tag", TAGS)
def test_a_status_of_an_older_request_backs_no_claim_of_a_new_one(tag: str) -> None:
    """The TD-144 scenario: the caller's older request told by its last digits, then a new one
    asked for and claimed with no action called. The claim names no number and its reply none,
    so the status backs nothing, and the record holds nothing."""
    model = FakeChat(calls(call("older_requests")), said(IS_OPEN[tag]), said(OPENED_NEW[tag]))
    rig = acting(model, older_requests)
    told = reply(rig.talker, STATUS_ASKED[tag])
    assert _spoken(told) == [IS_OPEN[tag]] and _blocked(told) == []
    claimed = reply(rig.talker, NEW_ASKED[tag])
    assert _spoken(claimed) == [] and _blocked(claimed) == ["unsupported_claim"]


@pytest.mark.parametrize("tag", TAGS)
def test_a_status_answer_that_names_the_digits_first_is_said_whole(tag: str) -> None:
    """The default phrase "It has been escalated" (any action's) passes after the clause of the
    same reply that named the request's last four digits; alone, in a later reply, it is blocked
    (the guard's fixed phrase said instead, as the ruling accepts)."""
    answer = said(f"{IS_OPEN[tag]} {ESCALATED[tag]}")
    model = FakeChat(calls(call("older_requests")), answer, said(ESCALATED[tag]))
    rig = acting(model, older_requests)
    told = reply(rig.talker, STATUS_ASKED[tag])
    assert _spoken(told) == [IS_OPEN[tag], ESCALATED[tag]] and _blocked(told) == []
    again = reply(rig.talker, ESCALATED_ASKED[tag])
    assert _spoken(again) == [] and _blocked(again) == ["unsupported_claim"]


@pytest.mark.parametrize(("turn", "claim"), OTHER_LANGUAGE)
def test_a_claim_in_the_replys_other_language_is_blocked_with_no_record(
    turn: TalkerTurn, claim: str
) -> None:
    events = reply(acting(FakeChat(said(claim))).talker, turn)
    assert _spoken(events) == [] and _blocked(events) == ["unsupported_claim"]


@pytest.mark.parametrize(("turn", "claim"), OTHER_LANGUAGE)
def test_a_claim_in_the_replys_other_language_passes_once_the_record_holds_it(
    turn: TalkerTurn, claim: str
) -> None:
    rig = acting(FakeChat(said(claim)))
    _written(rig)
    events = reply(rig.talker, turn)
    assert _spoken(events) == [claim] and _blocked(events) == []
