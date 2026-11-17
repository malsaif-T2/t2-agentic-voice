"""The question limit in the talker (agent/turn.py, agent/question_limit.py; D-085), on the fake
chat model: one reply says the talker's clauses up to and including its first question, and
stops before the next clause that asks one (`guard.questions_per_reply`, 1 by default).

- The second question and everything after it are no `SpokenClause`, however the model's text
  is cut into pieces, a question mark in a piece of its own or a question cut across two, Latin
  or Arabic; the clauses between the two questions are said; the limit holds across the reply's
  model requests; `ReplyDone` counts the clauses left unsaid.
- Only clauses said count: a question the guard blocked (under `drop_clause`), or a clause the
  stray-script filter left with no letter or digit, asks nothing.
- What it never changes: a tool call the model makes in the same request runs, and its result
  is kept for the turns after, but no request follows the stop, so nothing more of the reply is
  said; an action called after the stop is still read back; the next turn's request holds only
  what was said. With the setting None, every event is as before.
- With `guard.question_stop_drops_calls` (off by default, so the tests above hold today's
  behavior): the stopped request's tool calls and actions do not run, the log line counts them,
  the next turn's request holds none of them, and a request that asked one question and called
  a tool still runs it."""

from __future__ import annotations

import logging

import pytest
from t2_agentic_voice.actions.tools import tool
from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ReplyDone,
    SpokenClause,
    TalkerEvent,
    ToolEnded,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import (
    Conversation,
    PastTurn,
    SaidClause,
    SaidReply,
    TalkerTurn,
)
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.ports.chat_model import Done, TextDelta, Usage

from tests.t2_agentic_voice.agent.action_talk_support import acting
from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    Step,
    call,
    calls,
    kinds,
    reply,
    said,
    talker,
)

TURN = TalkerTurn(turn_id=1, words="My laptop will not start.", language="en")
# "laptopi ma yishtaghil", my laptop does not work.
SAUDI_TURN = TalkerTurn(turn_id=1, words="لابتوبي ما يشتغل", language="ar-SA")
TWO = "Is it urgent? Is it blocking your work? Tell me more."
DROP_CLAUSE = VoiceSettings(env="test", guard=GuardSettings(on_block="drop_clause"))
DROPS_CALLS = VoiceSettings(env="test", guard=GuardSettings(question_stop_drops_calls=True))


@tool(description="Do a made-up quick thing.")
async def quick() -> dict[str, bool]:
    return {"ok": True}


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpokenClause)]


def _unsaid(events: list[TalkerEvent]) -> int:
    [done] = [e for e in events if isinstance(e, ReplyDone)]
    return done.unsaid_clauses


def test_a_reply_says_its_first_question_and_stops_before_its_second() -> None:
    model = FakeChat(said(TWO))
    events = reply(talker(model), TURN)
    assert _spoken(events) == ["Is it urgent?"]
    assert kinds(events) == ["ModelRequested", "SpokenClause", "ModelReplied", "ReplyDone"]
    assert _unsaid(events) == 2
    assert model.closed == 1


def test_the_question_is_found_however_the_text_is_cut_into_pieces() -> None:
    cut_across = FakeChat(said("Is it ur", "gent? Is it bl", "ocking you", "? Then ", "tell me."))
    assert _spoken(reply(talker(cut_across), TURN)) == ["Is it urgent?"]
    alone = FakeChat(said("Is it urgent", "?", " I can help", ". Is it yours", "?"))
    events = reply(talker(alone), TURN)
    assert _spoken(events) == ["Is it urgent?", "I can help."]
    assert _unsaid(events) == 1


def test_an_arabic_question_mark_stops_the_reply_too() -> None:
    """ "hal hiya 'aajila? walla tigdar tintaDHir? gul li": is it urgent? or can you wait? tell
    me."""
    model = FakeChat(said("هل هي عاجلة", "؟ ولا تقدر", " تنتظر؟ قل لي."))
    events = reply(talker(model, language="ar-SA"), SAUDI_TURN)
    assert _spoken(events) == ["هل هي عاجلة؟"]
    assert _unsaid(events) == 2


def test_the_clauses_between_the_two_questions_are_said() -> None:
    model = FakeChat(said("Is it urgent? I can open a ticket. Is it blocking you? Thanks."))
    events = reply(talker(model), TURN)
    assert _spoken(events) == ["Is it urgent?", "I can open a ticket."]
    assert _unsaid(events) == 2


def test_one_question_then_steps_is_said_whole() -> None:
    steps = "Did you restart it? If not, hold the power key. Then wait ten seconds."
    events = reply(talker(FakeChat(said(steps))), TURN)
    assert _spoken(events) == [
        "Did you restart it?",
        "If not, hold the power key.",
        "Then wait ten seconds.",
    ]
    assert _unsaid(events) == 0


def test_the_limit_holds_across_the_replys_model_requests() -> None:
    model = FakeChat(
        calls(call("quick"), before="Is it the office laptop? "),
        said("First open Settings. Then press Reset. Did that work? Anything else?"),
    )
    events = reply(talker(model, quick), TURN)
    assert _spoken(events) == [
        "Is it the office laptop?",
        "First open Settings.",
        "Then press Reset.",
    ]
    assert _unsaid(events) == 2 and len(model.requests) == 2


def test_a_question_the_guard_blocked_asks_nothing() -> None:
    """Rule B blocks the ticket number no tool gave; under `drop_clause` the reply goes on, and
    its first question said is the next one."""
    model = FakeChat(said("Is your ticket 4521? Is it urgent? Thanks. Is it blocking you?"))
    events = reply(talker(model, settings=DROP_CLAUSE), TURN)
    assert [e.text for e in events if isinstance(e, ClauseBlocked)] == ["Is your ticket 4521?"]
    assert _spoken(events) == ["Is it urgent?", "Thanks."]
    assert _unsaid(events) == 1


def test_a_clause_the_stray_script_filter_emptied_asks_nothing() -> None:
    """ "重 →?" loses its Chinese character and is left an arrow and a question mark: no clause,
    so the reply's first question is the next one."""
    model = FakeChat(said("重 →? Is it urgent? Thanks. Is it blocking you?"))
    events = reply(talker(model), TURN)
    assert _spoken(events) == ["Is it urgent?", "Thanks."]
    assert _unsaid(events) == 1


def test_a_tool_call_in_the_same_request_still_runs_and_no_request_follows() -> None:
    model = FakeChat(
        [TextDelta(text=f"{TWO} "), call("quick"), Done(finish_reason="tool_calls")],
        said("Restart it."),
    )
    chat = talker(model, quick)
    events = reply(chat, TURN)
    assert kinds(events) == [
        "ModelRequested",
        "SpokenClause",
        "ModelReplied",
        "ToolBegan",
        "ToolEnded",
        "ReplyDone",
    ]
    assert _spoken(events) == ["Is it urgent?"]
    [ended] = [e for e in events if isinstance(e, ToolEnded)]
    assert ended.ok and ended.tool == "quick"
    assert len(model.requests) == 1  # nothing more of the reply would be said
    assert _unsaid(events) == 2


def test_the_next_turns_request_holds_only_what_was_said() -> None:
    """The heard history holds the clauses said (as the session hands it), and the talker kept
    the tool's call and result beside it, with none of the words left unsaid."""
    model = FakeChat(
        [TextDelta(text=f"{TWO} "), call("quick"), Done(finish_reason="tool_calls")],
        said("Thanks, noted."),
    )
    chat = talker(model, quick)
    first = reply(chat, TURN)
    heard = tuple(SaidClause(text=t, fate="played", played_fraction=1.0) for t in _spoken(first))
    past = Conversation(
        turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered", reply_id=1),),
        replies=(SaidReply(reply_id=1, turn_id=1, clauses=heard),),
    )
    reply(chat, TalkerTurn(turn_id=2, words="Yes, very.", language="en", conversation=past))
    messages = model.requests[1].messages
    assert [c.name for m in messages for c in m.tool_calls] == ["quick"]
    assert sum(m.role == "tool" for m in messages) == 1
    sent = " ".join(m.content for m in messages)
    assert "Is it urgent?" in sent
    assert "blocking" not in sent and "Tell me more" not in sent


def test_an_action_called_after_the_stop_is_still_read_back() -> None:
    turn = TalkerTurn(turn_id=1, words="My laptop will not start, open a request.", language="en")
    draft = {"category": "software", "summary": "the made-up laptop will not start"}
    model = FakeChat(calls(call("open_request", **draft), before=f"{TWO} "))
    events = reply(acting(model).talker, turn)
    assert _spoken(events) == ["Is it urgent?"]
    assert kinds(events)[-2:] == ["ReadBackRequested", "ReplyDone"]
    assert len(model.requests) == 1


def test_a_stop_drops_its_requests_tool_calls_when_the_setting_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    asked: list[Step] = [TextDelta(text=f"{TWO} "), call("quick"), call("quick", "c-2")]
    model = FakeChat([*asked, Done(finish_reason="tool_calls")], said("Noted."))
    chat = talker(model, quick, settings=DROPS_CALLS)
    events = reply(chat, TURN)
    assert kinds(events) == ["ModelRequested", "SpokenClause", "ModelReplied", "ReplyDone"]
    assert _spoken(events) == ["Is it urgent?"] and _unsaid(events) == 2
    assert len(model.requests) == 1
    [record] = [r for r in caplog.records if r.getMessage() == "talker_tool_call_ignored"]
    fields = dict(record.fields)  # type: ignore[attr-defined]
    assert (fields["turn_id"], fields["reason"], fields["calls"]) == (1, "question_limit", 2)
    reply(chat, TalkerTurn(turn_id=2, words="Yes, very.", language="en"))
    assert all(not m.tool_calls and m.role != "tool" for m in model.requests[1].messages)


def test_an_action_called_after_the_stop_is_not_read_back_when_the_setting_says_so() -> None:
    turn = TalkerTurn(turn_id=1, words="My laptop will not start, open a request.", language="en")
    draft = {"category": "software", "summary": "the made-up laptop will not start"}
    model = FakeChat(calls(call("open_request", **draft), before=f"{TWO} "))
    events = reply(acting(model, settings=DROPS_CALLS).talker, turn)
    assert _spoken(events) == ["Is it urgent?"]
    assert "ReadBackRequested" not in kinds(events) and kinds(events)[-1] == "ReplyDone"


def test_a_request_with_one_question_still_runs_its_tool_under_the_setting() -> None:
    model = FakeChat(
        calls(call("quick"), before="Is it the office laptop? "),
        said("First open Settings. Did that work?"),
    )
    events = reply(talker(model, quick, settings=DROPS_CALLS), TURN)
    assert kinds(events).count("ToolEnded") == 1 and len(model.requests) == 2
    assert _spoken(events) == ["Is it the office laptop?", "First open Settings."]


def test_with_no_limit_every_event_is_as_before() -> None:
    no_limit = VoiceSettings(env="test", guard=GuardSettings(questions_per_reply=None))
    events = reply(talker(FakeChat(said(TWO)), settings=no_limit), TURN)
    assert events == [
        ModelRequested(model="openai/gpt-oss-120b"),
        SpokenClause(text="Is it urgent?", language="en"),
        SpokenClause(text="Is it blocking your work?", language="en"),
        SpokenClause(text="Tell me more.", language="en"),
        ModelReplied(
            model="openai/gpt-oss-120b",
            usage=Usage(input_tokens=20, output_tokens=8),
            first_token_s=0.0,
        ),
        ReplyDone(),
    ]
