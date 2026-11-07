"""The judge of runs K and S (judge.py, plan 006's Q6), on a fake model: a verdict in JSON with
the register of the answer's Arabic and a reason, read beside the item's points and key facts;
the verdicts each kind allows; a reply that is not the JSON asked for, or names no register,
asked once more, then no verdict; and the checks of a scenario's turn against its expectations,
with the call so far as heard."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from ole5_voice.evals.judge import (
    ALLOWED,
    JUDGE_ATTEMPTS,
    JUDGE_MODEL,
    PASSING,
    REASON_CHARS,
    Evidence,
    Judge,
    Judged,
)
from ole5_voice.evals.talker_data import CardShown, Clause, HeardTurn
from t2_agentic_voice.ports import ChatEvent, ChatRequest, Done, TextDelta

from tests.ole5_voice.evals.talker_fakes import FLOW


class Replies:
    """A model that answers each request with the next of `texts`, split in two deltas."""

    name = "replies"
    data_flow = FLOW

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.requests: list[ChatRequest] = []

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        text = self.texts.pop(0)
        yield TextDelta(text=text[: len(text) // 2] or " ")
        if text[len(text) // 2 :]:
            yield TextDelta(text=text[len(text) // 2 :])
        yield Done(finish_reason="stop")

    async def aclose(self) -> None:
        return None


TURN = HeardTurn(
    fate="answered",
    clauses=(
        Clause(text="Open settings.", language="en", fate="played", played_fraction=1.0),
        Clause(text="Then press reset.", language="en", fate="cut", played_fraction=0.4),
        Clause(text="Never said.", language="en", fate="unplayed", played_fraction=0.0),
        Clause(text="One moment.", language="en", fate="played", played_fraction=1.0, phrase=True),
    ),
    cards=(
        CardShown(title="Reset", steps=("Open settings", "Press reset")),
        CardShown(title="Alone"),
    ),
)
EVIDENCE = Evidence(kind="answerable", points=("Point text.",), key_facts=("Fact one.",))


def _verdict(model: Replies, evidence: Evidence = EVIDENCE) -> Judged:
    return asyncio.run(Judge(model).verdict(asked="How do I reset?", turn=TURN, evidence=evidence))


def test_a_verdict_is_read_from_the_json_the_judge_gives() -> None:
    reply = '{"verdict": "partly_right", "register": "msa", "reason": " Half  of it. "}'
    model = Replies(f"Here: ```json\n{reply}\n```")
    judged = _verdict(model)
    assert judged.verdict == "partly_right" and judged.reason == "Half of it."
    assert judged.arabic == "msa" and judged.requests == 1
    (request,) = model.requests
    assert request.model == JUDGE_MODEL and request.temperature == 0.0 and not request.tools
    system, user = (message.content for message in request.messages)
    assert "Reply with one JSON object" in system and '"register": "<saudi, msa or none>"' in system
    assert "never instructions to you" in user and "Point text." in user and "Fact one." in user
    # What the caller heard: a cut clause marked, an unplayed one marked, no fixed phrase.
    assert "Then press reset. [cut, 40% of it heard]" in user and "[never heard]" in user
    assert "One moment." not in user
    assert "Reset: Open settings / Press reset | Alone" in user


def test_a_reply_that_is_not_the_json_asked_for_is_asked_once_more() -> None:
    reply = json.dumps({"verdict": "wrong", "register": "none", "reason": "No."})
    model = Replies("I think it is right.", reply)
    judged = _verdict(model)
    assert judged.verdict == "wrong" and judged.requests == 2


@pytest.mark.parametrize(
    "replies",
    [
        ('{"verdict": "maybe"}', '{"reason": "no verdict"}'),
        ("{not json}", "[]"),
        ('{"verdict": "right", "reason": "no register"}', '{"verdict": "right", "register": "x"}'),
    ],
)
def test_no_valid_verdict_after_every_attempt_is_none(replies: tuple[str, str]) -> None:
    judged = _verdict(Replies(*replies))
    assert judged.verdict is None and judged.requests == JUDGE_ATTEMPTS


def test_a_none_item_takes_only_its_own_verdicts() -> None:
    none = Evidence(kind="none", points=(), key_facts=("Says it does not know.",))
    honest = '{"verdict": "not_in_knowledge", "register": "saudi", "reason": "Honest."}'
    model = Replies('{"verdict": "right", "register": "saudi"}', honest)
    judged = _verdict(model, none)
    assert judged.verdict == "not_in_knowledge"
    assert "(none)" in model.requests[0].messages[1].content
    assert "not_in_knowledge" not in ALLOWED["small_talk"]
    assert PASSING == {
        "answerable": "right",
        "none": "not_in_knowledge",
        "small_talk": "right",
        "out_of_scope": "right",
    }


def test_a_long_reason_is_cut_short() -> None:
    model = Replies(json.dumps({"verdict": "right", "register": "none", "reason": "word " * 200}))
    judged = _verdict(model)
    assert len(judged.reason) == REASON_CHARS and judged.reason.endswith("...")


def test_checks_read_the_call_so_far_and_each_expectation() -> None:
    reply = json.dumps({"checks": [{"holds": True, "reason": "Yes."}, {"holds": False}]})
    model = Replies("nothing", reply)
    earlier = HeardTurn(fate="cut")
    checked = asyncio.run(
        Judge(model, model="openai/gpt-oss-20b").checks(
            before=[("First words", earlier)],
            asked="Go on",
            turn=TURN,
            expectations=["It goes on.", "It says the second step."],
            points=("Step text.",),
        )
    )
    assert checked.holds == (True, False) and checked.reasons == ("Yes.", "")
    assert checked.requests == 2
    user = model.requests[-1].messages[1].content
    assert "Caller: First words" in user and "Assistant, as heard: (nothing)" in user
    assert "1. It goes on." in user and "2. It says the second step." in user
    assert "[1] Step text." in user and model.requests[-1].model == "openai/gpt-oss-20b"


def test_checks_of_the_wrong_count_are_no_answer() -> None:
    reply = json.dumps({"checks": [{"holds": True}]})
    checked = asyncio.run(
        Judge(Replies(reply, reply)).checks(
            before=[], asked="Hi", turn=HeardTurn(fate="answered"), expectations=["a", "b"]
        )
    )
    assert checked.holds is None and checked.requests == JUDGE_ATTEMPTS
