"""The action runner's `propose` (actions/action_runner.py; the design's 6.4): the talker's
arguments parsed into the draft, each field at fault named and its value never repeated
(invariant 4); the action's `validate`; the caps, counted over confirmed actions in the outbox,
never over proposals; and the read-back rendered from the action's templates in the reply's
language, its fixed values through their labels, an ID digit by digit, and the library's lines
where the action leaves one out. A proposal writes nothing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from t2_agentic_voice.actions import spoken_lines
from t2_agentic_voice.actions.action import ActionContext, action
from t2_agentic_voice.actions.action_runner import PER_CALL, PER_DAY, ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.actions.runner import FAILED
from t2_agentic_voice.actions.tools import CallContext, ToolResult
from t2_agentic_voice.core.errors import ConfigurationError, ToolError
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_declaration import ReadBack, Say
from t2_agentic_voice.domain.action_lines import ActionLines, ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.yes_rule import is_confirmed

from tests.leaks import holding, shown
from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CLAIMS,
    DONE,
    ISSUED,
    SUMMARY,
    OpenRequest,
    RequestOpened,
    Rig,
    confirmed_of,
    context,
    request,
    timer_set,
)


def _proposed(rig: Rig, arguments: str, language: LanguageTag = "en") -> Any:
    return asyncio.run(rig.runner.propose(request(arguments), context(language), clock=rig.clock))


def test_a_draft_is_read_back_from_the_actions_templates_in_the_reply_language() -> None:
    rig = Rig()
    plan = asyncio.run(rig.plan())
    assert isinstance(plan, ReadBackPlan)
    assert (plan.action, plan.tool_call_id, plan.language) == ("open_request", "tool-call-1", "en")
    assert plan.summary.text == f"A software request: {SUMMARY}."
    assert plan.question == SpokenLine(text="Shall I send it?", spoken="Shall I send it?")
    assert plan.asked_again.text == "Sorry, shall I send it?"
    assert plan.declined.text == "I have not opened anything."
    assert plan.sending.text == "One moment, opening your request."
    assert plan.send_words == ("open it",) and plan.max_attempts == 2
    assert OpenRequest.model_validate_json(plan.draft_json).summary == SUMMARY
    assert asyncio.run(rig.outbox.entries()) == ()  # a proposal writes nothing
    assert rig.backend.writes == []


def test_a_fixed_value_is_said_through_its_label_in_the_language() -> None:
    rig = Rig()
    plan = asyncio.run(rig.plan("ar-SA"))
    assert plan.summary.text == f"بفتح طلب برامج: {SUMMARY}."
    assert plan.sending.text == "لحظة، أفتح لك طلب برامج."
    assert plan.asked_again.text == "ما سمعتك، أرسل طلب برامج؟"
    assert plan.send_words == ("افتحه",) and plan.language == "ar-SA"
    hardware = _proposed(rig, '{"category": "hardware", "summary": "x"}', "ar")
    assert hardware.summary.text == "بفتح طلب أجهزة: x."
    english = _proposed(rig, '{"category": "hardware", "summary": "x"}')
    assert english.summary.text == "A hardware request: x."  # no English label: as written


@pytest.mark.parametrize(
    ("arguments", "told"),
    [
        (
            '{"category": "furniture", "summary": "x"}',
            "invalid arguments: `category`: Input should be 'hardware' or 'software'",
        ),
        ('{"summary": "x"}', "invalid arguments: `category`: Field required"),
        (
            '{"category": "software", "summary": "x", "confirmed": true}',
            "invalid arguments: `confirmed`: Extra inputs are not permitted",
        ),
        ("{not json", "the arguments are not JSON: give a JSON object of the tool's parameters"),
    ],
    ids=["outside the fixed set", "missing", "a consent the talker claims", "not json"],
)
def test_an_invalid_draft_goes_back_to_the_talker_with_its_field_named(
    arguments: str, told: str
) -> None:
    """Invariant 4: a value outside a fixed set, a missing field or one the draft does not hold
    is refused before anything else, and a field claiming consent is nothing but an extra key
    (invariant 1: nothing in a draft stands in for the caller's yes)."""
    rig = Rig()
    result = _proposed(rig, arguments)
    assert result == ToolResult(data={"error": told}, ok=False, failure="bad_arguments")
    assert asyncio.run(rig.outbox.entries()) == () and rig.backend.writes == []


def test_a_refused_value_is_never_repeated(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    secret = "made-up-category-4400"
    result = _proposed(Rig(), f'{{"category": "{secret}", "summary": "{SUMMARY}"}}')
    assert not result.ok
    assert holding(secret, {"result": str(result.data), **shown(caplog=caplog)}) == []
    assert holding(SUMMARY, {"result": str(result.data), **shown(caplog=caplog)}) == []


def test_nothing_a_proposal_returns_is_a_confirmed_action() -> None:
    """Invariant 1: the talker's call gets a read-back, never a confirmation; only the yes rule
    issues one, from words heard after that read-back."""
    plan = asyncio.run(Rig().plan())
    assert not is_confirmed(plan)
    assert not any(is_confirmed(value) for value in plan.model_dump().values())


def _validating(validate: Any) -> Rig:
    return Rig(validate=validate)


def test_validate_may_reject_the_draft_and_the_talker_is_told_why() -> None:
    async def strict(ctx: CallContext, draft: OpenRequest) -> OpenRequest:
        raise ToolError("That category is closed today.")

    result = _proposed(_validating(strict), '{"category": "software", "summary": "x"}')
    assert result == ToolResult(
        data={"error": "That category is closed today."}, ok=False, failure="draft_rejected"
    )


def test_validate_may_keep_a_changed_draft_or_the_one_it_was_given() -> None:
    seen: list[str] = []

    def tidy(ctx: CallContext, draft: OpenRequest) -> OpenRequest:  # a sync one, in a thread
        seen.append(ctx.call_id)
        return OpenRequest(category="hardware", summary=draft.summary.upper())

    plan = _proposed(_validating(tidy), '{"category": "software", "summary": "x"}')
    assert plan.summary.text == "A hardware request: X." and seen == [CALL_ID]

    async def checks(ctx: CallContext, draft: OpenRequest) -> None:
        return None

    kept = _proposed(_validating(checks), '{"category": "software", "summary": "x"}')
    assert kept.summary.text == "A software request: x."


@pytest.mark.parametrize("returned", ["not a draft", {"category": "furniture"}])
def test_a_validate_that_fails_or_returns_no_draft_gives_a_generic_failure(
    returned: Any, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(ctx: CallContext, draft: OpenRequest) -> Any:
        if returned == "not a draft":
            raise RuntimeError(SUMMARY)
        return returned

    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    result = _proposed(_validating(broken), f'{{"category": "software", "summary": "{SUMMARY}"}}')
    assert result == ToolResult(data={"error": FAILED}, ok=False, failure="validate_failed")
    assert holding(SUMMARY, shown(caplog=caplog)) == []


def test_a_validate_past_the_actions_timeout_is_cancelled() -> None:
    cancelled: list[bool] = []

    async def slow(ctx: CallContext, draft: OpenRequest) -> OpenRequest:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return draft

    rig = Rig(validate=slow, timeout_s=3.0)

    async def proposed() -> Any:
        work = asyncio.ensure_future(rig.runner.propose(request(), context(), clock=rig.clock))
        await timer_set(rig.clock, 3.0)
        await rig.clock.advance(3.0)
        proposed = await work
        await asyncio.sleep(0)
        return proposed

    result = asyncio.run(proposed())
    assert result == ToolResult(data={"error": FAILED}, ok=False, failure="validate_failed")
    assert cancelled == [True]


def test_the_per_call_cap_counts_confirmed_actions_never_proposals() -> None:
    rig = Rig(max_per_call=1)

    async def scenario() -> tuple[Any, Any, Any, Any]:
        first = await rig.plan()
        again = await rig.plan()  # a proposal counts for nothing
        await rig.run(confirmed_of(first))
        capped = await rig.runner.propose(request(), context(), clock=rig.clock)
        other_call = await rig.runner.propose(request(), context(call_id="call-2"), clock=rig.clock)
        return first, again, capped, other_call

    first, again, capped, other_call = asyncio.run(scenario())
    assert isinstance(first, ReadBackPlan) and isinstance(again, ReadBackPlan)
    assert capped == ToolResult(data={"error": PER_CALL}, ok=False, failure="cap_per_call")
    assert isinstance(other_call, ReadBackPlan)


def test_the_per_caller_cap_counts_a_days_confirmed_actions_whatever_became_of_them() -> None:
    rig = Rig("reject", max_per_call=5)
    rig.runner = ActionRunner([rig.action], outbox=rig.outbox, per_caller_per_day=2)

    async def scenario() -> list[Any]:
        told = []
        for call_id in ("call-1", "call-2", "call-3"):
            plan = await rig.runner.propose(request(), context(call_id=call_id), clock=rig.clock)
            told.append(plan)
            if isinstance(plan, ReadBackPlan):
                await rig.run(confirmed_of(plan), call_id=call_id)
        await rig.clock.advance(24 * 3600.0 + 1.0)
        told.append(await rig.runner.propose(request(), context("en"), clock=rig.clock))
        return told

    first, second, third, next_day = asyncio.run(scenario())
    assert isinstance(first, ReadBackPlan) and isinstance(second, ReadBackPlan)
    assert third == ToolResult(data={"error": PER_DAY}, ok=False, failure="cap_per_caller")
    assert isinstance(next_day, ReadBackPlan)


def test_an_action_the_agent_does_not_have_is_answered_with_those_it_has() -> None:
    rig = Rig()
    result = asyncio.run(rig.runner.propose(request(name="delete_all"), context()))
    assert result == ToolResult(
        data={"error": "there is no action named `delete_all`; the actions are: open_request"},
        ok=False,
        failure="no_such_action",
    )


async def _plain(draft: OpenRequest) -> RequestOpened:
    return RequestOpened(number="1")


def test_a_line_the_action_leaves_out_is_the_librarys(monkeypatch: pytest.MonkeyPatch) -> None:
    library = ActionLines(
        sending="Library sending.",
        failed="Library failed.",
        unknown="Library unknown.",
        declined="Library declined.",
        asked_again="Library asked again.",
    )
    asked: list[str] = []

    def lines(tag: LanguageTag) -> ActionLines:
        asked.append(tag)
        return library

    monkeypatch.setattr(spoken_lines, "default_action_lines", lines)
    bare = action(
        description="Open a made-up request.",
        read_back=ReadBack({"en": ("A {category} request: {summary}.", "Send it?")}),
        done=DONE,
        claims=CLAIMS,
    )(_plain)
    runner = ActionRunner([bare], outbox=MemoryOutbox())
    plan = asyncio.run(runner.propose(request(name="_plain"), context()))
    assert isinstance(plan, ReadBackPlan)
    assert (plan.sending.text, plan.declined.text, plan.asked_again.text) == (
        "Library sending.",
        "Library declined.",
        "Library asked again.",
    )
    assert plan.sending.spoken == "Library sending." and set(asked) == {"en"}


async def _numbered(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
    return RequestOpened(number="1")


def test_an_id_is_said_digit_by_digit_in_groups_and_shown_as_issued() -> None:
    from t2_agentic_voice.actions.spoken_lines import render

    line = render("Number {number:id}, tag {tag:id}.", {"number": ISSUED, "tag": "LT-00423"}, "en")
    assert line.text == f"Number {ISSUED}, tag LT-00423."
    assert line.spoken == (
        "Number two zero two six, one one one zero, eight two zero zero, zero one two three, "
        "tag LT- zero zero four two three."
    )
    arabic = render("رقم {number:id}", {"number": "٢٠٢٦"}, "ar-SA")
    assert arabic.text == "رقم ٢٠٢٦" and arabic.spoken == "رقم اثنان صفر اثنان ستة"


def test_a_draft_the_read_back_cannot_say_is_told_back() -> None:
    empty = ReadBack({"en": ("{summary}", "Send it?")})
    made = action(description="Open a made-up request.", read_back=empty, done=DONE, claims=CLAIMS)(
        _numbered
    )
    runner = ActionRunner([made], outbox=MemoryOutbox())
    result = asyncio.run(
        runner.propose(request('{"category": "software", "summary": " "}', "_numbered"), context())
    )
    assert isinstance(result, ToolResult) and result.failure == "read_back_unsaid"


def test_the_runner_takes_only_actions_each_with_its_own_name() -> None:
    rig = Rig()
    with pytest.raises(ConfigurationError, match="FIX:"):
        ActionRunner([rig.action, rig.action], outbox=rig.outbox)
    with pytest.raises(ConfigurationError, match="FIX:"):
        ActionRunner([object()], outbox=rig.outbox)  # type: ignore[list-item]
    assert [schema.name for schema in rig.runner.schemas()] == ["open_request"]
    assert rig.runner.action("open_request") is rig.action and rig.runner.action("x") is None


def test_an_outbox_that_cannot_be_read_refuses_the_proposal() -> None:
    class Unreadable(MemoryOutbox):
        async def count(self, **_: Any) -> int:
            raise OSError("disk")

    rig = Rig(outbox=Unreadable())
    result = asyncio.run(rig.runner.propose(request(), context(), clock=rig.clock))
    assert result == ToolResult(data={"error": FAILED}, ok=False, failure="outbox_unread")


def test_the_say_shorthand_with_no_text_for_the_language_falls_to_the_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        spoken_lines,
        "default_action_lines",
        lambda tag: ActionLines(
            sending="s", failed="f", unknown="u", declined="d", asked_again="a"
        ),
    )
    line = spoken_lines.line_of(Say(en="English only."), "sending", {}, "ar-SA")
    assert line == SpokenLine(text="s", spoken="s")
