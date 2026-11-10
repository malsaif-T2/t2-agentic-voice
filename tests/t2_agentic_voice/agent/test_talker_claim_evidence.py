"""What backs a claim, and which phrases claim, on the talker's clauses with the real rule A
(agent/speech_guard.py, domain/claims.py; the design's 8.2; docs/SECURITY.md, invariant 2,
GP-08), so no stand-in hides either from the guard:

- A `reports_on` tool's result that succeeded but holds no ID-shaped token, a status that found
  nothing, backs no claim: the claim the model writes after it is blocked as with no status at
  all, while a status that holds a number backs it (test_talker_claims.py).
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


def test_a_status_that_holds_a_number_backs_the_claim() -> None:
    model = FakeChat(calls(call("one_request")), said(CLAIM))
    events = reply(acting(model, one_request).talker, ENGLISH)
    assert _spoken(events) == [CLAIM] and _blocked(events) == []


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
