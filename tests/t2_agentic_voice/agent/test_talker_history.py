"""The model's context from the heard history (agent/context.py; plan 006, "What voice-first
means here", items 1 and 2): each past reply as the caller heard it, an unplayed clause never as
said and a cut one marked with how much of it played; the turn answered now whole, a stop word
included, saying what it was said over and naming the reply it cut; the turns and replies in the
order they came; a turn the drop rule dropped left out."""

from __future__ import annotations

from t2_agentic_voice.agent.context import WENT_ON, history, said, turn_message
from t2_agentic_voice.agent.talker import SpokenClause
from t2_agentic_voice.core.conversation import (
    Conversation,
    PastTurn,
    SaidClause,
    SaidReply,
    TalkerTurn,
)
from t2_agentic_voice.domain.ports.chat_model import ChatMessage

from tests.t2_agentic_voice.agent.chat_support import FakeChat, reply, talker
from tests.t2_agentic_voice.agent.chat_support import said as entry

PLAYED = SaidClause(text="Open the portal.", fate="played", played_fraction=1.0)
CUT = SaidClause(text="Then choose Forgot password.", fate="cut", played_fraction=0.43)
UNPLAYED = SaidClause(text="The code lasts 10 minutes.", fate="unplayed", played_fraction=0.0)
GREETING = SaidReply(
    reply_id=0, clauses=(SaidClause(text="Hi, how can I help?", fate="played", played_fraction=1),)
)
ANSWER = SaidReply(reply_id=1, turn_id=0, clauses=(PLAYED, CUT, UNPLAYED))
ASKED = PastTurn(turn_id=0, words="How do I reset my password?", fate="cut", reply_id=1)
SO_FAR = Conversation(turns=(ASKED,), replies=(GREETING, ANSWER))


def _roles_and_texts(messages: list[ChatMessage]) -> list[tuple[str, str]]:
    return [(m.role, m.content) for m in messages]


def test_an_unplayed_clause_never_reaches_the_model_and_a_cut_one_is_marked() -> None:
    assert said(ANSWER) == "Open the portal. Then choose Forgot password. [cut: about 40% heard]"
    assert "10 minutes" not in str(_roles_and_texts(history(SO_FAR, exchanges={}, notes={})))
    unheard = SaidReply(reply_id=2, turn_id=1, clauses=(UNPLAYED,))
    assert said(unheard) is None


def test_the_call_reaches_the_model_in_the_order_it_was_heard() -> None:
    later = PastTurn(turn_id=1, words="ok thanks", fate="answered", reply_id=3)
    notice = SaidReply(
        reply_id=2,
        clauses=(SaidClause(text="Something went wrong.", fate="played", played_fraction=1),),
    )
    thanks = SaidReply(
        reply_id=3,
        turn_id=1,
        clauses=(SaidClause(text="You're welcome.", fate="played", played_fraction=1),),
    )
    conversation = Conversation(turns=(ASKED, later), replies=(GREETING, ANSWER, notice, thanks))
    assert _roles_and_texts(history(conversation, exchanges={}, notes={})) == [
        ("assistant", "Hi, how can I help?"),
        ("user", "How do I reset my password?"),
        ("assistant", "Open the portal. Then choose Forgot password. [cut: about 40% heard]"),
        ("assistant", "Something went wrong."),
        ("user", "ok thanks"),
        ("assistant", "You're welcome."),
    ]


def test_a_dropped_turn_or_one_with_no_words_is_left_out_and_one_gone_over_is_marked() -> None:
    echo = PastTurn(turn_id=1, words="Open the portal", fate="dropped")
    mumble = PastTurn(turn_id=2, words="", fate="command")
    listening = PastTurn(turn_id=3, words="mm hmm", fate="went_on")
    conversation = Conversation(turns=(ASKED, echo, mumble, listening), replies=(ANSWER,))
    users = [m.content for m in history(conversation, exchanges={}, notes={}) if m.role == "user"]
    assert users == ["How do I reset my password?", f"mm hmm {WENT_ON}"]


def test_a_turn_said_over_a_reply_says_so_and_names_the_reply_it_cut() -> None:
    turn = TalkerTurn(
        turn_id=1,
        words="stop, only the second step",
        over_reply=1,
        cut_reply=1,
        conversation=SO_FAR,
    )
    assert turn_message(turn) == ChatMessage.user(
        "stop, only the second step [said over your reply 1, which it cut]"
    )
    named = history(SO_FAR, exchanges={}, notes={}, named=frozenset({1}))
    assert named[-1].content.startswith("[reply 1] Open the portal.")


def test_a_turn_that_stopped_a_reply_before_it_played_says_so() -> None:
    unheard = SaidReply(reply_id=2, turn_id=1, clauses=(UNPLAYED,))
    conversation = Conversation(turns=(ASKED,), replies=(ANSWER, unheard))
    turn = TalkerTurn(
        turn_id=2, words="wait, another question", cut_reply=2, conversation=conversation
    )
    assert turn_message(turn).content == (
        "wait, another question [it stopped your reply 2 before any of it was heard]"
    )
    over = TalkerTurn(
        turn_id=2, words="go on", over_reply=1, cut_reply=2, conversation=conversation
    )
    assert turn_message(over).content == (
        "go on [said over your reply 1] [it stopped your reply 2 before any of it was heard]"
    )


def test_the_talker_sends_the_heard_call_and_the_turn_whole_with_its_stop_word() -> None:
    """Any wording reaches the model as said: no word list in the talker."""
    model = FakeChat(entry("Sure, the second step: choose Forgot password."))
    turn = TalkerTurn(
        turn_id=1,
        words="وقف، بس الخطوة الثانية",
        language="ar",
        over_reply=1,
        cut_reply=1,
        conversation=SO_FAR,
    )
    reply(talker(model), turn)
    messages = model.requests[0].messages
    assert [m.role for m in messages] == ["system", "assistant", "user", "assistant", "user"]
    assert messages[-1].content == "وقف، بس الخطوة الثانية [said over your reply 1, which it cut]"
    assert messages[3].content.startswith("[reply 1] Open the portal. Then choose Forgot")
    assert all("10 minutes" not in m.content for m in messages[1:])


def test_a_turn_joined_after_a_resumed_hold_reaches_the_model_as_one_turn() -> None:
    """The session joins the words (plan 006, Q2); the talker sends them as one message."""
    model = FakeChat(entry("Sure."))
    reply(talker(model), TalkerTurn(turn_id=1, words="how do I reset my password on the portal"))
    users = [m.content for m in model.requests[0].messages if m.role == "user"]
    assert users == ["how do I reset my password on the portal"]


def test_a_turn_said_alone_that_cut_a_heard_reply_names_it() -> None:
    turn = TalkerTurn(turn_id=1, words="another question", cut_reply=1, conversation=SO_FAR)
    assert turn_message(turn).content == "another question [it cut your reply 1]"


def test_a_note_the_model_copies_from_its_history_is_never_spoken() -> None:
    """The history's notes on the model's own replies are taken out of what it writes, however
    its stream cuts them; other text in square brackets is said as written."""
    pieces = ("[re", "ply 1] Open the portal. [cut: about ", "40% heard] Then press [re", "set].")
    events = reply(talker(FakeChat(entry(*pieces))), TalkerTurn(turn_id=1, words="and then?"))
    spoken = [event.text for event in events if isinstance(event, SpokenClause)]
    assert spoken == ["Open the portal.", "Then press [reset]."]
