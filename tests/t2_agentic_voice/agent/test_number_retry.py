"""A number held back sent once more (`guard.retry_ids`, agent/clause_gate.py), and the turn's
retries (`guard.retries_per_turn`): the owner's calls of 2026-11-22, where a model added two
fares itself and rule B blocked the sum. By default a clause holding a number no result of the
call gives is blocked as before, its note left and the notice said in its place (not
`sent_again`); with the setting on, its request ends there, unsaid and with no notice, and is
sent once more with what it said and `ID_HELD`, one past the turn's limit. A claim and a number
share the turn's retries; once they are spent, a clause goes as `guard.on_block` says. Every
sentence and fare is made up for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.actions.tools import ToolResult, tool
from t2_agentic_voice.agent.clause_gate import CLAIM_HELD, ID_HELD
from t2_agentic_voice.agent.context import BLOCKED
from t2_agentic_voice.agent.talker import ChatTalker, ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.guard import GuardSettings, OnBlock
from t2_agentic_voice.domain.action_declaration import Claims

from tests.t2_agentic_voice.agent.chat_support import FakeChat, call, calls, reply, said, talker

TURN = TalkerTurn(turn_id=1, words="What do the two made-up fares come to?", language="en")
SUM = "Both come to 2488 riyals."  # 1059 + 1429, worked out by the model: no result gives it
FARES = "The fares are 1059 and 1429 riyals."
CLAIM = "I've booked your fare."


@tool(name="read_fares", description="Read the made-up fares.")
async def read_fares() -> ToolResult:
    return ToolResult(data={"fares": [1059, 1429]})


@tool(name="book_fare", description="Book the made-up fare.", claims=Claims({"en": [CLAIM]}))
async def book_fare() -> ToolResult:
    return ToolResult(data={"status": "not_booked"})


def _settings(guard: GuardSettings | None = None) -> VoiceSettings:
    return VoiceSettings(env="test", guard=guard or GuardSettings())


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpokenClause)]


def _blocked(events: list[TalkerEvent]) -> list[ClauseBlocked]:
    return [e for e in events if isinstance(e, ClauseBlocked)]


def _notes_after(chat: ChatTalker) -> list[str]:
    """The system messages of the next turn's request, the first turn in its history."""
    after = FakeChat(said("Okay."))
    chat.model = after
    past = Conversation(turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered"),))
    reply(chat, TalkerTurn(turn_id=2, words="Thanks.", language="en", conversation=past))
    return [m.content for m in after.requests[0].messages if m.role == "system"]


def test_by_default_a_number_no_result_gives_is_blocked_as_before() -> None:
    model = FakeChat(calls(call("read_fares")), said("One moment. ", SUM, " Shall I book one?"))
    chat = talker(model, read_fares, settings=_settings())
    events = reply(chat, TURN)
    [blocked] = _blocked(events)
    assert (blocked.reason, blocked.unsupported, blocked.sent_again) == (
        "unsupported_id",
        ("2488",),
        False,  # the session says the notice in its place
    )
    assert _spoken(events) == ["One moment."] and len(model.requests) == 2
    assert BLOCKED in _notes_after(chat)


def test_a_number_held_back_is_sent_once_more_with_what_was_said_and_its_note() -> None:
    model = FakeChat(
        calls(call("read_fares")),
        said("One moment. ", SUM, " Anything else?"),
        said(FARES),
    )
    chat = talker(model, read_fares, settings=_settings(GuardSettings(retry_ids=True)))
    events = reply(chat, TURN)
    assert _spoken(events) == ["One moment.", FARES]
    [blocked] = _blocked(events)
    assert (blocked.text, blocked.reason, blocked.sent_again) == (SUM, "unsupported_id", True)
    again = model.requests[2].messages
    assert [m.content for m in again[-3:-1]] == ["One moment.", ID_HELD]
    assert again[-3].role == "assistant" and again[-2].role == "system"
    assert model.requests[2].tools  # not the last request: the tool that gives it is offered
    assert len(model.requests) == 3
    assert BLOCKED not in _notes_after(chat)  # answered anew: no note of it


@pytest.mark.parametrize(
    ("on_block", "spoken"),
    [("drop_rest", ["One moment."]), ("drop_clause", ["One moment.", "Anything else?"])],
)
def test_two_retries_a_turn_send_a_second_block_again_and_a_third_goes_as_on_block_says(
    on_block: OnBlock, spoken: list[str]
) -> None:
    model = FakeChat(
        calls(call("read_fares")),
        said(SUM),
        said("One moment. ", SUM),
        said(SUM, " Anything else?"),
    )
    guard = GuardSettings(retry_ids=True, retries_per_turn=2, on_block=on_block)
    chat = talker(model, read_fares, settings=_settings(guard))
    events = reply(chat, TURN)
    assert [b.sent_again for b in _blocked(events)] == [True, True, False]
    assert _spoken(events) == spoken
    assert len(model.requests) == 4  # two past the turn's three, no more
    assert [m.content for m in model.requests[3].messages].count(ID_HELD) == 2
    assert BLOCKED in _notes_after(chat)


def test_a_claim_and_a_number_share_the_turns_retries() -> None:
    model = FakeChat(calls(call("read_fares")), said(SUM), said(CLAIM))
    guard = GuardSettings(retry_ids=True, retry_claims=True)
    events = reply(talker(model, read_fares, book_fare, settings=_settings(guard)), TURN)
    assert [(b.reason, b.sent_again) for b in _blocked(events)] == [
        ("unsupported_id", True),
        ("unsupported_claim", False),
    ]
    assert len(model.requests) == 3


def test_a_claim_held_back_after_a_number_reads_the_claims_note() -> None:
    model = FakeChat(calls(call("read_fares")), said(SUM), said(CLAIM), said(FARES))
    guard = GuardSettings(retry_ids=True, retry_claims=True, retries_per_turn=2)
    events = reply(talker(model, read_fares, book_fare, settings=_settings(guard)), TURN)
    assert _spoken(events) == [FARES]
    again = model.requests[3].messages  # nothing said before either: each its note alone
    assert [(m.role, m.content) for m in again[-3:-1]] == [
        ("system", ID_HELD),
        ("system", CLAIM_HELD),
    ]
