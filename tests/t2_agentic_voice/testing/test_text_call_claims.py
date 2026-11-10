"""`TextCall`'s rule A check with the real rule (testing/text_checks.py; the design's 8.2;
docs/SECURITY.md, invariant 2), on the tests' scripted talker, which no guard stands before, so
`call.violations` alone says what a guard let pass, and reads a claim as the live guard does
(test_talker_claim_evidence.py):

- a `reports_on` tool's result that holds no ID-shaped token, a status that found nothing, backs
  no claim, while one that holds the booking's number does;
- a claim the talker wrote in the reply's other language is one, the phrases every language's,
  so with no record it is a violation."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import JsonValue
from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

from tests.t2_agentic_voice.testing.action_support import CLAIM, agent_with
from tests.t2_agentic_voice.testing.text_call_support import Ran, ScriptedCall, Step, answer

CLAIMED = f"Your {CLAIM}."
NO_RECORD = "turn 0 claimed"


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
    def script(turn: TalkerTurn) -> list[Step]:
        return steps

    async def scene() -> tuple[str, ...]:
        async with ScriptedCall(script, agent=agent_with(tools=tools), language=language) as call:
            await call.user("is my visit booked")
            await call.advance(10.0)
            return call.violations

    return asyncio.run(scene())


@pytest.mark.parametrize(
    ("data", "backed"),
    [({"state": "none"}, False), ({"number": "5101", "state": "booked"}, True)],
    ids=["found_nothing", "holds_the_number"],
)
def test_a_status_backs_a_claim_only_when_it_holds_an_id(data: JsonValue, backed: bool) -> None:
    tool, ran = _status(data)
    found = _violations([ran, *answer(CLAIMED)], tools=(tool,), language="en")
    assert [violation.startswith(NO_RECORD) for violation in found] == ([] if backed else [True])


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
