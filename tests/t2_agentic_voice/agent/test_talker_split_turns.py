"""A turn split by a pause reads as one (agent/context.py; the owner's ruling of 2026-11-12 after
the live call `LTLrFU`: "what tickets submitted with my", a pause, "email", answered as a
question about email). The caller's words that stop the reply to their last turn before any of
it was heard go on with that turn: one user message, in order, the calls and results the talker
kept of the earlier turn before it, where they came; past turns read the same. A reply the
caller heard, a command, or a turn said over a heard reply keeps the turns apart."""

from __future__ import annotations

from t2_agentic_voice.actions.tools import CallContext, tool
from t2_agentic_voice.agent.context import continued, history, turn_message
from t2_agentic_voice.core.conversation import (
    Conversation,
    PastTurn,
    SaidClause,
    SaidReply,
    TalkerTurn,
)
from t2_agentic_voice.domain.ports.chat_model import ChatMessage

from tests.t2_agentic_voice.agent.chat_support import FakeChat, call, calls, reply, said, talker

FIRST = "what tickets submitted with my"
HEARD = SaidClause(text="Hi, how can I help?", fate="played", played_fraction=1.0)
UNPLAYED = SaidClause(text="Here are your tickets.", fate="unplayed", played_fraction=0.0)
GREETING = SaidReply(reply_id=0, clauses=(HEARD,))
UNHEARD = SaidReply(reply_id=1, turn_id=1, clauses=(UNPLAYED,))
EARLIER = PastTurn(turn_id=1, words=FIRST, fate="rolled_back", reply_id=1)
SO_FAR = Conversation(turns=(EARLIER,), replies=(GREETING, UNHEARD))


def _users(messages: list[ChatMessage]) -> list[str]:
    return [m.content for m in messages if m.role == "user"]


def test_words_that_stop_an_unheard_reply_go_on_with_the_turn_before() -> None:
    turn = TalkerTurn(turn_id=2, words="email", cut_reply=1, conversation=SO_FAR)
    assert continued(turn) == (EARLIER,)
    assert turn_message(turn).content == f"{FIRST} email"
    assert _users(history(SO_FAR, exchanges={}, notes={}, continued=continued(turn))) == []


def test_the_talker_sends_one_turn_after_what_it_found_for_the_first_part() -> None:
    @tool(description="The caller's tickets.")
    async def ticket_status(ctx: CallContext) -> dict[str, str]:
        return {"ticket": "0002 is new"}

    model = FakeChat(calls(call("ticket_status")), said("Tickets."), said("Ticket 0002 is new."))
    chat = talker(model, ticket_status)
    reply(chat, TalkerTurn(turn_id=1, words=FIRST))  # its reply then cut before it played
    reply(chat, TalkerTurn(turn_id=2, words="email", cut_reply=1, conversation=SO_FAR))
    messages = model.requests[-1].messages
    assert [m.role for m in messages] == ["system", "assistant", "assistant", "tool", "user"]
    assert messages[-1].content == f"{FIRST} email"
    assert "0002 is new" in messages[3].content


def test_a_turn_split_twice_reads_as_one() -> None:
    start = PastTurn(turn_id=1, words="I tried to send", fate="rolled_back", reply_id=1)
    middle = PastTurn(turn_id=2, words="a message", fate="rolled_back", reply_id=2)
    replies = (GREETING, UNHEARD, SaidReply(reply_id=2, turn_id=2, clauses=(UNPLAYED,)))
    so_far = Conversation(turns=(start, middle), replies=replies)
    turn = TalkerTurn(turn_id=3, words="but it got stuck", cut_reply=2, conversation=so_far)
    assert continued(turn) == (start, middle)
    assert turn_message(turn).content == "I tried to send a message but it got stuck"


def test_past_turns_split_by_a_pause_read_as_one() -> None:
    later = PastTurn(turn_id=2, words="email", fate="answered", reply_id=2)
    answer = SaidReply(
        reply_id=2,
        turn_id=2,
        clauses=(SaidClause(text="Ticket 0002 is new.", fate="played", played_fraction=1.0),),
    )
    conversation = Conversation(turns=(EARLIER, later), replies=(GREETING, UNHEARD, answer))
    assert [(m.role, m.content) for m in history(conversation, exchanges={}, notes={})] == [
        ("assistant", "Hi, how can I help?"),
        ("user", f"{FIRST} email"),
        ("assistant", "Ticket 0002 is new."),
    ]


def test_a_heard_reply_a_command_or_a_heard_overlap_keeps_the_turns_apart() -> None:
    heard = SaidReply(reply_id=1, turn_id=1, clauses=(HEARD,))
    told = Conversation(turns=(EARLIER,), replies=(GREETING, heard))
    cut_heard = TalkerTurn(turn_id=2, words="email", cut_reply=1, conversation=told)
    assert continued(cut_heard) == ()
    assert turn_message(cut_heard).content == "email [it cut your reply 1]"
    over_heard = TalkerTurn(
        turn_id=2, words="email", over_reply=0, cut_reply=1, conversation=SO_FAR
    )
    assert continued(over_heard) == ()
    alone = TalkerTurn(turn_id=2, words="email", conversation=SO_FAR)
    assert (continued(alone), turn_message(alone).content) == ((), "email")
    stop = PastTurn(turn_id=2, words="stop", fate="command")
    after = PastTurn(turn_id=3, words="what about drafts", fate="answered")
    conversation = Conversation(turns=(EARLIER, stop, after), replies=(GREETING, UNHEARD))
    assert _users(history(conversation, exchanges={}, notes={})) == [
        FIRST,
        "stop",
        "what about drafts",
    ]


def test_a_notice_heard_between_two_turns_keeps_them_apart() -> None:
    notice = SaidReply(reply_id=2, clauses=(HEARD,))
    later = PastTurn(turn_id=2, words="email", fate="answered", reply_id=3)
    conversation = Conversation(turns=(EARLIER, later), replies=(GREETING, UNHEARD, notice))
    assert _users(history(conversation, exchanges={}, notes={})) == [FIRST, "email"]
