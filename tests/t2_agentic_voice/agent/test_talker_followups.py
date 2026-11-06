"""What the talker keeps of its tools between turns (agent/tool_calls.py's `Memory`; plan 006):
the calls and results of a past turn reach the next turn's request, which the heard history does
not hold, so "only the second step" is answered from the card the caller saw; a number a tool
gave may be said in a later turn; and a tool whose barge-in is `finish` outlives its cut reply,
its result reaching the next turn. Every passage is written for the test."""

from __future__ import annotations

import asyncio
from typing import Any

from t2_agentic_voice.actions.knowledge import NAME, knowledge_tool
from t2_agentic_voice.actions.tools import CallContext, tool
from t2_agentic_voice.agent.talker import SpokenClause, TalkerEvent
from t2_agentic_voice.core.conversation import (
    Conversation,
    PastTurn,
    SaidClause,
    SaidReply,
    TalkerTurn,
)
from t2_agentic_voice.domain.ports.knowledge import Passage
from t2_agentic_voice.testing.knowledge_fake import FakeKnowledgeBase
from t2_agentic_voice.voice.session.scope import CancelScope

from tests.t2_agentic_voice.agent.chat_support import (
    FakeChat,
    call,
    calls,
    reply,
    said,
    settle,
    talker,
)
from tests.t2_agentic_voice.fakes import FakeClock

TURN = TalkerTurn(turn_id=1, words="How do I reset my password?", language="en")
RESET = Passage(
    id="made-up-001",
    title="Reset a password",
    text="Open the portal and choose Forgot password. The code 8841 lasts 10 minutes.",
    steps=("Open the portal", "Choose Forgot password", "Enter code 8841"),
    score=0.7,
)


def _search(kb: FakeKnowledgeBase) -> Any:
    return knowledge_tool(kb, description="Search the help articles.", progress="searching")


def test_the_tool_calls_and_results_reach_the_next_turn() -> None:
    """ "Only the second step" is answered from the result the history does not hold."""
    model = FakeChat(
        calls(call(NAME, query="reset")),
        said("The steps are on your screen."),
        said("Choose Forgot password."),
    )
    chat = talker(model, _search(FakeKnowledgeBase([RESET])))
    reply(chat, TURN)
    heard = SaidReply(
        reply_id=1,
        turn_id=1,
        clauses=(
            SaidClause(text="The steps are on your screen.", fate="played", played_fraction=1),
        ),
    )
    so_far = Conversation(
        turns=(PastTurn(turn_id=1, words=TURN.words, fate="answered", reply_id=1),),
        replies=(heard,),
    )
    events = reply(chat, TalkerTurn(turn_id=2, words="only the second step", conversation=so_far))
    messages = model.requests[-1].messages
    assert [m.role for m in messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert messages[2].tool_calls[0].name == NAME and messages[2].content == ""
    assert "Choose Forgot password" in messages[3].content
    assert messages[4].content == "The steps are on your screen."
    assert SpokenClause(text="Choose Forgot password.", language="en") in events


def test_a_number_a_tool_gave_may_be_said_in_a_later_turn() -> None:
    model = FakeChat(calls(call(NAME, query="code")), said("Use code 8841."), said("It is 8841."))
    chat = talker(model, _search(FakeKnowledgeBase([RESET])))
    reply(chat, TURN)
    events = reply(chat, TalkerTurn(turn_id=2, words="which code again?"))
    assert SpokenClause(text="It is 8841.", language="en") in events


def test_a_finish_tool_outlives_its_reply_and_its_result_reaches_the_next_turn() -> None:
    release = asyncio.Event()

    @tool(description="Made up.", on_interrupt="finish", timeout_s=30.0)
    async def lasting(ctx: CallContext) -> dict[str, str]:
        await release.wait()
        return {"found": "9137 in the record"}

    model = FakeChat(calls(call("lasting")), said("It is 9137."))
    chat = talker(model, lasting)

    async def run() -> list[TalkerEvent]:
        scope = CancelScope(name="reply-1", clock=chat.clock)
        task = scope.start(_drain(chat, TURN, scope), name="reply-1-talker")
        await settle()
        await scope.cancel()  # the barge-in: the reply goes, the tool finishes
        release.set()
        await settle()
        assert task.cancelled()
        cut = PastTurn(turn_id=1, words=TURN.words, fate="rolled_back", reply_id=1)
        turn = TalkerTurn(turn_id=2, words="and?", conversation=Conversation(turns=(cut,)))
        return [e async for e in chat.reply(turn, scope=_open())]

    events = asyncio.run(run())
    assert [m.role for m in model.requests[-1].messages][1:] == [
        "user",
        "assistant",
        "tool",
        "user",
    ]
    assert SpokenClause(text="It is 9137.", language="en") in events


async def _drain(chat: Any, turn: TalkerTurn, scope: CancelScope) -> None:
    async for _ in chat.reply(turn, scope=scope):
        pass


def _open() -> CancelScope:
    return CancelScope(name="reply-2", clock=FakeClock())
