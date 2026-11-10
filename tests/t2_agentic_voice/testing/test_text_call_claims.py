"""`TextCall`'s rule A check with the real rule (testing/text_checks.py; the design's 8.2;
docs/SECURITY.md, invariant 2), on the tests' scripted talker, which no guard stands before, so
`call.violations` alone says what a guard let pass, and reads a claim as the live guard does
(test_talker_claim_evidence.py):

- a `reports_on` tool's result that holds no ID-shaped token, a status that found nothing, backs
  no claim, while one that holds the booking's number backs a claim that names it;
- a status backs a claim with no number only in the reply whose earlier clause named one of its
  numbers, a clause the guard would have passed (the owner's ruling of 2026-11-10 on TD-144,
  "Number or same reply"): in a later reply it is a violation; and on the real talker the guard
  blocks that claim, so nothing is heard and the checks stay clean;
- a claim the talker wrote in the reply's other language is one, the phrases every language's,
  so with no record it is a violation."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import JsonValue
from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.events import GuardBlocked
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.testing.text_call import TextCall

from tests.t2_agentic_voice.testing.action_call_support import (
    STATUS,
    Backend,
    agent_of,
    events,
    model,
    said_texts,
    say,
)
from tests.t2_agentic_voice.testing.action_support import CLAIM, Visit, agent_with
from tests.t2_agentic_voice.testing.text_call_support import Ran, ScriptedCall, Step, answer

CLAIMED = f"Your {CLAIM}."
NO_RECORD = "turn 0 claimed"
# The visit's status told by its number, then the claim with no number, in each language:
# «ziyaartak raqm 5101 maHjooza», your visit number 5101 is booked; «sajjalt lak az-ziyaara»,
# I registered the visit for you (a default phrase, any action's).
TOLD: dict[LanguageTag, str] = {
    "en": "Your visit 5101 is on the desk.",
    "ar-SA": "زيارتك رقم 5101 على المكتب.",
}
NO_NUMBER: dict[LanguageTag, str] = {"en": CLAIMED, "ar-SA": "سجلت لك الزيارة."}
# The caller asking how their visit stands, then for a new one: «wish Saar 'ala ziyaarti?», what
# became of my visit?; «iHjiz li waHda thaanya», book me another one; and the real talker's
# agent's claim of it with no number, a default phrase in each language.
ASKED: dict[LanguageTag, str] = {"en": "How is my visit?", "ar-SA": "وش صار على زيارتي؟"}
AGAIN: dict[LanguageTag, str] = {"en": "Book me another one.", "ar-SA": "احجز لي وحدة ثانية"}
BOOKED_NEW: dict[LanguageTag, str] = {
    "en": "I've booked another one for you.",
    "ar-SA": NO_NUMBER["ar-SA"],
}


def _status(data: JsonValue) -> tuple[Tool, Ran]:
    """A tool that reports on the action, and its call, which returned `data`."""

    async def status() -> ToolResult:
        return ToolResult(data=data)

    tool = Tool.from_function(
        status, name="visit_status", description="A visit's status.", reports_on=["book_visit"]
    )
    request = ToolCallRequest(id="t-9", name="visit_status", arguments="{}")
    return tool, Ran(request, ToolResult(data=data))


def _violations(
    steps: list[Step], *, tools: tuple[Tool, ...] = (), language: LanguageTag
) -> tuple[str, ...]:
    return _turns([steps], tools=tools, language=language)


def _turns(
    replies: list[list[Step]], *, tools: tuple[Tool, ...] = (), language: LanguageTag
) -> tuple[str, ...]:
    """The call's violations once the caller spoke a turn for each of `replies`, the talker
    answering the turn `n` with `replies[n]`."""

    def script(turn: TalkerTurn) -> list[Step]:
        return replies[turn.turn_id]

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script, agent=agent_with(tools=tools), language=language) as call:
            for n in range(len(replies)):
                await call.user(f"is my visit booked {n}")
                await call.advance(10.0)
            return call.violations

    return asyncio.run(scene())


@pytest.mark.parametrize(
    ("data", "claim", "backed"),
    [
        ({"state": "none"}, CLAIMED, False),
        ({"number": "5101", "state": "booked"}, f"Your {CLAIM}, number 5101.", True),
    ],
    ids=["found_nothing", "holds_the_number"],
)
def test_a_status_backs_a_claim_only_when_it_holds_an_id(
    data: JsonValue, claim: str, backed: bool
) -> None:
    tool, ran = _status(data)
    found = _violations([ran, *answer(claim)], tools=(tool,), language="en")
    assert [violation.startswith(NO_RECORD) for violation in found] == ([] if backed else [True])


@pytest.mark.parametrize("language", ["en", "ar-SA"])
def test_a_claim_with_no_number_passes_only_in_the_reply_that_named_the_status_number(
    language: LanguageTag,
) -> None:
    tool, ran = _status({"number": "5101", "state": "booked"})
    told, claim = TOLD[language], NO_NUMBER[language]
    same = _violations(
        [ran, *answer(told, claim, language=language)], tools=(tool,), language=language
    )
    assert same == ()
    later = _turns(
        [[ran, *answer(told, language=language)], answer(claim, language=language)],
        tools=(tool,),
        language=language,
    )
    assert [violation.startswith("turn 1 claimed") for violation in later] == [True]


def test_a_clause_the_guard_would_block_names_no_number_for_the_reply() -> None:
    """The earlier clause named the status's number beside one with no evidence: the guard
    would have blocked it, so it was never said, and the claim after it is a violation too."""
    tool, ran = _status({"number": "5101", "state": "booked"})
    found = _violations(
        [ran, *answer("Your visit 5101 is on the desk, and 8899 too.", CLAIMED)],
        tools=(tool,),
        language="en",
    )
    assert [violation.split(" ")[2] for violation in found] == ["said", "claimed"]


@pytest.mark.parametrize("language", ["en", "ar-SA"])
def test_the_guard_blocks_a_claim_on_an_older_status_and_nothing_is_heard(
    language: LanguageTag,
) -> None:
    """On the real talker: the status of a visit booked before this call, told by its number,
    then a new visit claimed with no action called. The guard blocks the claim, so the caller
    hears none of it, and the checks, which read it as the guard does, stay clean."""
    backend = Backend()
    backend.desk.book("r-earlier", Visit(room="R-204", note="the projector is broken"))
    claim = BOOKED_NEW[language]
    llm = model(
        {ASKED[language]: ScriptedLLM.call_tool(STATUS), AGAIN[language]: say(claim)},
        after={STATUS: say(TOLD[language])},
    )

    async def scene() -> tuple[str, ...]:
        async with TextCall(agent_of(backend), llm=llm, language=language) as call:
            told = await call.user(ASKED[language])
            await call.advance(30.0)
            told.expect.said(contains=TOLD[language])
            asked = await call.user(AGAIN[language])
            await call.advance(30.0)
            asked.expect.blocked()
            assert all(claim not in text for text in said_texts(call))
            blocked = [e.reason for e in events(call) if isinstance(e, GuardBlocked)]
            assert blocked == ["unsupported_claim"] and backend.writes == 0
            return call.violations

    assert asyncio.run(scene()) == ()


@pytest.mark.parametrize(
    ("language", "claim"),
    [
        ("en", "سجلت لك الزيارة."),  # sajjalt lak az-ziyaara: I registered the visit for you
        ("ar-SA", "I have created it for you."),
    ],
    ids=["arabic_in_english", "english_in_arabic"],
)
def test_a_claim_in_the_replys_other_language_is_a_violation(
    language: LanguageTag, claim: str
) -> None:
    found = _violations(answer(claim, language=language), language=language)
    assert [violation.startswith(NO_RECORD) for violation in found] == [True]
