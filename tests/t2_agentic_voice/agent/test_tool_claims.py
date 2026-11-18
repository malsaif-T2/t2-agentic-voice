"""The output guard's rule A on a tool that writes and declares its claims (actions/tools.py's
`Tool.claims`, `ToolResult.done`; agent/speech_guard.py's `claimants`), and a claim held back sent
once more (`guard.retry_claims`, agent/clause_gate.py): a clause that says the tool's write was
done is blocked until a result of it in the call was `done`, and then passes with that result's
numbers; a result not done, a failed one, or another tool's backs nothing. An agent with no
action is held to its tools' phrases and the settings' added ones, never the library's defaults
(an honest "nothing has been booked yet" is said). With the setting on,
the turn's first blocked claim ends its request, unsaid and with no notice, and the request is
sent once more with what it said and a note, one past the turn's limit; a second goes as
`guard.on_block` says. Every sentence is written for the test."""

from __future__ import annotations

from t2_agentic_voice.actions.tools import ToolResult, tool
from t2_agentic_voice.agent.clause_gate import CLAIM_HELD
from t2_agentic_voice.agent.context import CLAIM_BLOCKED
from t2_agentic_voice.agent.talker import ChatTalker, ClauseBlocked, SpokenClause, TalkerEvent
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import Conversation, PastTurn, TalkerTurn
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.domain.action_declaration import Claims

from tests.t2_agentic_voice.agent.chat_support import FakeChat, call, calls, reply, said, talker

TURN = TalkerTurn(turn_id=1, words="Yes, place my made-up order.", language="en")
CLAIMS = Claims({"en": ["I've placed your order"]})
CLAIM = "I've placed your order, 740 riyals in all."
ASKED_AGAIN = "Your order comes to 740 riyals: shall I place it?"
RETRY = GuardSettings(retry_claims=True)


@tool(name="place_order", description="Place the made-up order.", claims=CLAIMS)
async def placed() -> ToolResult:
    return ToolResult(data={"status": "placed", "total": 740}, done=True)


@tool(name="place_order", description="Place the made-up order.", claims=CLAIMS)
async def not_placed() -> ToolResult:
    return ToolResult(data={"status": "not_confirmed", "total": 740})


@tool(name="place_order", description="Place the made-up order.", claims=CLAIMS)
async def failed_placed() -> ToolResult:
    return ToolResult(data={"status": "placed", "total": 740}, done=True, ok=False)


@tool(name="read_order", description="Read the made-up order.")
async def read_order() -> ToolResult:
    return ToolResult(data={"status": "placed", "total": 740}, done=True)


def _notes_after(chat: ChatTalker) -> list[str]:
    """The system messages of the next turn's request, the first turn in its history."""
    after = FakeChat(said("Okay."))
    chat.model = after
    past = Conversation(turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered"),))
    reply(chat, TalkerTurn(turn_id=2, words="Thanks.", language="en", conversation=past))
    return [m.content for m in after.requests[0].messages if m.role == "system"]


def _spoken(events: list[TalkerEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, SpokenClause)]


def _blocked(events: list[TalkerEvent]) -> list[ClauseBlocked]:
    return [e for e in events if isinstance(e, ClauseBlocked)]


def _settings(guard: GuardSettings | None = None, requests: int = 3) -> VoiceSettings:
    llm = LlmSettings(max_requests_per_turn=requests)
    return VoiceSettings(env="test", guard=guard or GuardSettings(), llm=llm)


def test_a_tools_claim_with_no_done_result_is_blocked() -> None:
    model = FakeChat(calls(call("place_order")), said(CLAIM))
    events = reply(talker(model, not_placed, settings=_settings()), TURN)
    [blocked] = _blocked(events)
    assert (blocked.reason, blocked.sent_again) == ("unsupported_claim", False)
    assert _spoken(events) == []


def test_a_done_result_backs_the_tools_claim_and_its_numbers() -> None:
    model = FakeChat(calls(call("place_order")), said(CLAIM))
    events = reply(talker(model, placed, settings=_settings()), TURN)
    assert _spoken(events) == [CLAIM] and _blocked(events) == []


def test_a_failed_result_or_another_tools_backs_no_claim() -> None:
    for tools in ((failed_placed,), (not_placed, read_order)):
        model = FakeChat(calls(call("read_order"), call("place_order", call_id="c-2")), said(CLAIM))
        events = reply(talker(model, *tools, settings=_settings()), TURN)
        assert [b.reason for b in _blocked(events)] == ["unsupported_claim"], tools


def test_a_claim_held_back_is_sent_once_more_with_what_was_said_and_a_note() -> None:
    model = FakeChat(
        calls(call("place_order")),
        said("One moment. ", CLAIM, " Anything else?"),
        said(ASKED_AGAIN),
    )
    chat = talker(model, not_placed, settings=_settings(RETRY))
    events = reply(chat, TURN)
    assert _spoken(events) == ["One moment.", ASKED_AGAIN]
    [blocked] = _blocked(events)
    assert blocked.sent_again and blocked.text == CLAIM
    again = model.requests[2].messages
    assert [m.content for m in again[-3:-1]] == ["One moment.", CLAIM_HELD]
    assert again[-3].role == "assistant" and again[-2].role == "system"
    assert model.requests[2].tools  # not the last request: the tools are offered again
    assert CLAIM_BLOCKED not in _notes_after(chat)  # answered anew: no note of it


def test_a_claim_held_back_in_the_last_request_is_sent_one_past_the_limit() -> None:
    model = FakeChat(calls(call("place_order")), said(CLAIM), said(ASKED_AGAIN))
    events = reply(talker(model, not_placed, settings=_settings(RETRY, requests=2)), TURN)
    assert _spoken(events) == [ASKED_AGAIN]
    assert len(model.requests) == 3 and model.requests[2].tools == ()


def test_a_second_claim_in_the_turn_goes_as_on_block_says() -> None:
    model = FakeChat(said(CLAIM), said(CLAIM, " Anything else?"))
    chat = talker(model, not_placed, settings=_settings(RETRY))
    events = reply(chat, TURN)
    assert [b.sent_again for b in _blocked(events)] == [True, False]
    assert _spoken(events) == [] and len(model.requests) == 2
    assert CLAIM_BLOCKED in _notes_after(chat)


def test_a_tool_alone_is_held_to_its_phrases_not_the_librarys_defaults() -> None:
    honest = "No, nothing has been booked yet."  # the defaults hold "has been booked"
    model = FakeChat(calls(call("place_order")), said(honest))
    events = reply(talker(model, not_placed, settings=_settings(RETRY)), TURN)
    assert _spoken(events) == [honest] and _blocked(events) == []
    assert len(model.requests) == 2  # nothing sent again


def test_a_tool_alone_is_still_held_to_the_settings_added_phrases() -> None:
    added = GuardSettings.model_validate({"claims": {"en": ["all done for you"]}})
    model = FakeChat(calls(call("place_order")), said("All done for you."))
    events = reply(talker(model, not_placed, settings=_settings(added)), TURN)
    assert [b.reason for b in _blocked(events)] == ["unsupported_claim"]
