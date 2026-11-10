"""The talker's side of an action (agent/turn.py, agent/tool_calls.py; the design's 6.4): the
action offered beside the tools, its schema the draft's alone; its call proposed to the action
runner, the read-back the reply's last event and no request after it; a refusal back to the
model, which may speak again; one action a request; rule C, the text after the call dropped
unspoken (GP-08); a tool call that claims the caller's yes confirming nothing (invariant 1,
GP-08); and a declined read-back answered by the model in its own words, a correction called
again (the owner's ruling, plan 007). Rule A: test_talker_claims.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from t2_agentic_voice.agent import turn as turn_module
from t2_agentic_voice.agent.context import DECLINED, turn_message
from t2_agentic_voice.agent.prompt import ACTION_RULES, RULES
from t2_agentic_voice.agent.talker import ClauseBlocked, ReadBackRequested, SpokenClause, ToolEnded
from t2_agentic_voice.agent.tool_calls import ONE_AT_A_TIME, READ_BACK
from t2_agentic_voice.core.conversation import (
    Conversation,
    DeclinedAction,
    DeclineKind,
    PastTurn,
    TalkerTurn,
)
from t2_agentic_voice.domain.ports.chat_model import TextDelta

from tests.leaks import holding, shown
from tests.t2_agentic_voice.actions.action_support import ISSUED
from tests.t2_agentic_voice.agent.action_talk_support import FakeClaims, acting, fake_rule_a, rows
from tests.t2_agentic_voice.agent.chat_support import FakeChat, call, calls, kinds, reply, said

TURN = TalkerTurn(
    turn_id=1, words="My made-up laptop will not start, open a request.", language="en"
)
SUMMARY = "the made-up laptop will not start"
DRAFT: dict[str, Any] = {"category": "software", "summary": SUMMARY}
AGENT_FOLDER = Path(turn_module.__file__).parent


@pytest.fixture(autouse=True)
def rule_a(monkeypatch: pytest.MonkeyPatch) -> FakeClaims:
    return fake_rule_a(monkeypatch)


def _after(turn_id: int, words: str, **declined: Any) -> TalkerTurn:
    """The caller's turn after TURN was answered, declining its read-back when told how."""
    past = Conversation(turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered"),))
    no = DeclinedAction(action="open_request", words=words, **declined) if declined else None
    return TalkerTurn(turn_id=turn_id, words=words, language="en", declined=no, conversation=past)


def test_the_action_is_offered_beside_the_tools_its_schema_the_drafts_alone() -> None:
    model = FakeChat(said("Which laptop is it?"))
    reply(acting(model).talker, TURN)
    [request] = model.requests
    [schema] = request.tools
    assert schema.name == "open_request"
    properties: Any = schema.parameters["properties"]
    assert sorted(properties) == ["category", "summary"]
    assert schema.parameters["additionalProperties"] is False  # no field beyond the draft
    assert f"\n{RULES}\n{ACTION_RULES}\nToday is" in request.messages[0].content


def test_an_action_call_is_read_back_the_replys_last_event_and_nothing_is_written() -> None:
    model = FakeChat(calls(call("open_request", **DRAFT), before="Let me read that back. "))
    rig = acting(model)
    events = reply(rig.talker, TURN)
    assert kinds(events) == [
        "ModelRequested",
        "SpokenClause",
        "ModelReplied",
        "ToolBegan",
        "ToolEnded",
        "ReadBackRequested",
        "ReplyDone",
    ]
    assert len(model.requests) == 1  # no request after the read-back
    [read_back] = [e for e in events if isinstance(e, ReadBackRequested)]
    plan = read_back.plan
    assert (plan.action, plan.tool_call_id, plan.language) == ("open_request", "c-1", "en")
    assert json.loads(plan.draft_json) == DRAFT
    assert plan.summary.text == f"A software request: {SUMMARY}."
    assert plan.question.text == "Shall I send it?"
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.ok and ended.failure is None
    assert json.loads(ended.result) == {"status": READ_BACK}
    assert rig.backend.writes == [] and rig.runner.record("call-1").entries() == ()
    assert rows(rig.outbox) == ()


def test_the_model_reads_that_its_call_is_read_back_in_the_turns_after() -> None:
    model = FakeChat(calls(call("open_request", **DRAFT)), said("Sure."))
    rig = acting(model)
    reply(rig.talker, TURN)
    reply(rig.talker, _after(2, "what happens now?"))
    tool_messages = [m.content for m in model.requests[1].messages if m.role == "tool"]
    assert tool_messages == [f'<data tool="open_request">{{"status": "{READ_BACK}"}}</data>']


def test_text_after_the_action_call_is_dropped_unspoken_and_unblocked() -> None:
    """Rule C (GP-08): what the model writes after the call, in its request, is never spoken,
    what the splitter held before it neither, and no clause of it is blocked: dropped."""
    model = FakeChat(
        [
            TextDelta(text="Sure. I am opening it for you"),
            call("open_request", **DRAFT),
            TextDelta(text=f" Done, I've opened request {ISSUED}. "),
            TextDelta(text="It is all sorted."),
        ]
    )
    events = reply(acting(model).talker, TURN)
    assert [e.text for e in events if isinstance(e, SpokenClause)] == ["Sure."]
    assert not any(isinstance(e, ClauseBlocked) for e in events)
    assert "ReadBackRequested" in kinds(events) and len(model.requests) == 1


def test_text_after_a_refused_action_call_is_dropped_and_the_next_request_speaks() -> None:
    model = FakeChat(
        [
            call("open_request", category="printers", summary=SUMMARY),
            TextDelta(text=f"I've opened request {ISSUED}."),
        ],
        said("Is it a hardware or a software problem?"),
    )
    events = reply(acting(model).talker, TURN)
    spoken = [e.text for e in events if isinstance(e, SpokenClause)]
    assert spoken == ["Is it a hardware or a software problem?"]
    assert "ReadBackRequested" not in kinds(events)


def test_a_refusal_goes_back_to_the_model_naming_the_field_never_its_value() -> None:
    model = FakeChat(
        calls(call("open_request", category="printers", summary=SUMMARY)),
        said("Is it hardware or software?"),
    )
    rig = acting(model)
    events = reply(rig.talker, TURN)
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert (ended.tool, ended.ok, ended.failure) == ("open_request", False, "bad_arguments")
    [framed] = [m.content for m in model.requests[1].messages if m.role == "tool"]
    assert "`category`" in framed and "printers" not in framed
    assert rows(rig.outbox) == () and rig.backend.writes == []


def test_one_action_a_request_the_second_refused_unasked() -> None:
    model = FakeChat(
        calls(
            call("open_request", "c-1", **DRAFT),
            call("open_request", "c-2", category="hardware", summary="a second one"),
        )
    )
    events = reply(acting(model).talker, TURN)
    [read_back] = [e for e in events if isinstance(e, ReadBackRequested)]
    assert read_back.plan.tool_call_id == "c-1"
    ended = {e.call_id: e for e in events if isinstance(e, ToolEnded)}
    assert ended["c-2"].failure == "one_at_a_time"
    assert json.loads(ended["c-2"].result) == {"error": ONE_AT_A_TIME}


@pytest.mark.parametrize("claim", ["confirmed", "caller_said_yes", "consent"])
def test_a_tool_call_that_claims_the_callers_yes_is_refused_and_confirms_nothing(
    claim: str,
) -> None:
    """Invariant 1 (GP-08): an argument that says the caller agreed is a field the draft does
    not hold, refused by its name; nothing is read back or written."""
    arguments: dict[str, Any] = {**DRAFT, claim: True}
    model = FakeChat(calls(call("open_request", "c-1", **arguments)), said("Sorry."))
    rig = acting(model)
    events = reply(rig.talker, TURN)
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.failure == "bad_arguments" and f"`{claim}`" in ended.result
    assert "ReadBackRequested" not in kinds(events)
    assert rows(rig.outbox) == () and rig.backend.writes == []


def test_a_valid_call_whose_model_says_the_caller_agreed_is_only_read_back() -> None:
    """Invariant 1 (GP-08): however sure the model is of a yes, its call only asks for the
    read-back; only the yes rule, over the caller's heard words, issues a confirmed action."""
    model = FakeChat(
        calls(call("open_request", **DRAFT), before="The caller already said yes, so sending. "),
    )
    rig = acting(model)
    events = reply(rig.talker, TURN)
    assert [type(e).__name__ for e in events if not isinstance(e, SpokenClause)][-2:] == [
        "ReadBackRequested",
        "ReplyDone",
    ]
    assert rig.backend.writes == [] and rows(rig.outbox) == ()
    assert rig.runner.record("call-1").entries() == ()


def test_a_tool_named_to_confirm_is_no_tool_and_confirms_nothing() -> None:
    model = FakeChat(calls(call("confirm_open_request", answer="yes")), said("Sorry."))
    rig = acting(model)
    events = reply(rig.talker, TURN)
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.failure == "no_such_tool"
    assert rows(rig.outbox) == () and rig.backend.writes == []


def test_no_module_of_the_talker_can_reach_a_confirmed_action() -> None:
    """Invariant 1 (GP-08): the talker's layer names neither the yes rule nor what it issues,
    nor runs a job, so no tool argument has a path to a write."""
    for module in sorted(AGENT_FOLDER.glob("*.py")):
        source = module.read_text(encoding="utf-8")
        for name in ("ConfirmedAction", "yes_rule", "decide(", "is_confirmed", ".run(confirmed"):
            assert name not in source, (module.name, name)


def test_a_plain_no_is_answered_by_the_model_in_its_own_words() -> None:
    model = FakeChat(
        calls(call("open_request", **DRAFT)),
        said("All right, nothing was sent. What else can I do?"),
        said("Sure."),
    )
    rig = acting(model)
    reply(rig.talker, TURN)
    events = reply(rig.talker, _after(2, "no", kind="no"))
    assert [e.text for e in events if isinstance(e, SpokenClause)] == [
        "All right, nothing was sent.",
        "What else can I do?",
    ]
    note = DECLINED["no"].format(action="open_request")
    assert model.requests[1].messages[-1].content == f"no {note}"
    later = _after(3, "thanks").model_copy(
        update={
            "conversation": Conversation(
                turns=(
                    PastTurn(turn_id=1, words=TURN.words, fate="answered"),
                    PastTurn(turn_id=2, words="no", fate="answered"),
                )
            )
        }
    )
    reply(rig.talker, later)
    contents = [(m.role, m.content) for m in model.requests[2].messages]
    assert contents.index(("user", "no")) + 1 == contents.index(("system", note))


def test_a_correction_is_answered_with_the_action_called_again_and_read_back_anew() -> None:
    model = FakeChat(
        calls(call("open_request", **DRAFT)),
        calls(call("open_request", "c-2", category="hardware", summary=SUMMARY)),
    )
    rig = acting(model)
    reply(rig.talker, TURN)
    events = reply(rig.talker, _after(2, "it is hardware, not software", kind="correction"))
    assert "call it again" in model.requests[1].messages[-1].content
    [read_back] = [e for e in events if isinstance(e, ReadBackRequested)]
    assert json.loads(read_back.plan.draft_json)["category"] == "hardware"
    assert rig.backend.writes == []


def test_nothing_the_talker_logs_of_an_action_holds_the_draft(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    model = FakeChat(
        [call("open_request", **DRAFT), TextDelta(text=f"Opened {ISSUED}, {SUMMARY}.")],
    )
    reply(acting(model).talker, TURN)
    surfaces = shown(caplog=caplog)
    assert holding(SUMMARY, surfaces) == [] and holding(ISSUED, surfaces) == []


@pytest.mark.parametrize("kind", ["no", "correction", "unclear"])
def test_each_decline_has_its_note_naming_the_action_never_the_words(kind: DeclineKind) -> None:
    turn = _after(2, f"made-up words {SUMMARY}", kind=kind)
    note = DECLINED[kind].format(action="open_request")
    assert turn_message(turn).content == f"made-up words {SUMMARY} {note}"
    assert SUMMARY not in note


def test_a_turn_replied_twice_keeps_its_declined_note_once() -> None:
    """An early start cancelled and the turn replied again (plan 006, Q2) keeps one note."""
    model = FakeChat(calls(call("open_request", **DRAFT)), said("Sure."), said("Sure."))
    rig = acting(model)
    reply(rig.talker, TURN)
    declined = _after(2, "no", kind="no")
    reply(rig.talker, declined)
    reply(rig.talker, declined)
    note = DECLINED["no"].format(action="open_request")
    kept = rig.talker._memory.exchanges[2]
    assert [m.content for m in kept].count(note) == 1
