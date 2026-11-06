"""The model's context (plan 006, "What voice-first means here", items 1 and 2): the call as the
caller heard it, built from the `Conversation` the session hands with each turn
(core/conversation.py), never from what the talker wrote.

- **A reply** is the model's own message holding the clauses that played, then the clause a
  stop cut, if any, marked with how much of it played (agent/prompt.py's `CUT_MARK`); a clause
  that never played is not in it, and a reply none of whose clauses played is no message.
- **A turn** of the caller's is a user message holding its heard words, whole: a stop word, a
  repeat request, "go on" or a correction reach the model as said, for it to understand from
  the history (no word list here). A turn the drop rule judged the agent's own voice
  (`dropped`), or with no words, is none. One the reply went on over is marked so.
- **The turn answered now** says, after its words, whether it was said over a reply and which
  reply it cut, each named by its number; a reply so named carries its number in its message,
  in a note the prompt tells the model is never its to write.
- **What only the talker knew** goes beside the heard history, in its place: the tool calls and
  results it kept of a past turn (agent/talker.py), after that turn's words, and the developer
  note of a clause the output guard held back from that turn's reply.

The history holds two lists, the turns and the replies, each in order; they are told apart in
time by the turn each reply answers: a reply follows every turn up to the one it answers, and a
reply that answers none (the greeting, a notice) follows the turns its earlier replies
answered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from t2_agentic_voice.agent.prompt import CUT_MARK
from t2_agentic_voice.core.conversation import Conversation, PastTurn, SaidReply, TalkerTurn
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.domain.ports.chat_model import ChatMessage

# The notes the model reads beside the caller's words and its own.
WENT_ON = "[said over your reply, which went on]"
BLOCKED = (
    "Note: the output guard held back a sentence of the reply to this turn, unspoken: it gave "
    "an ID-shaped number that no tool result or caller's words held. Never say such a number."
)


def said(reply: SaidReply, *, named: bool = False) -> str | None:
    """What the caller heard of `reply`, as the model's message reads it (the module's
    docstring); None when none of it played."""
    heard: list[str] = []
    for clause in reply.clauses:
        if clause.fate == "played":
            heard.append(clause.text)
        elif clause.fate == "cut":
            percent = round(clause.played_fraction * 10) * 10
            heard.append(f"{clause.text} {CUT_MARK.format(percent=percent)}")
    if not heard:
        return None
    text = " ".join(heard)
    return f"[reply {reply.reply_id}] {text}" if named else text


def _turn_text(turn: PastTurn) -> str | None:
    """A past turn of the caller's as the model's user message reads it; None for one with
    nothing to read."""
    if turn.fate == "dropped" or not turn.words.strip():
        return None
    return f"{turn.words} {WENT_ON}" if turn.fate == "went_on" else turn.words


def _before(turn: PastTurn, reply: SaidReply) -> bool:
    """Whether the caller's `turn` came before `reply` (the module's docstring)."""
    if reply.turn_id is not None:
        return turn.turn_id <= reply.turn_id
    return turn.reply_id is not None and turn.reply_id < reply.reply_id


def turn_message(turn: TalkerTurn) -> ChatMessage:
    """The turn answered now, its words whole, then what it was said over and what it cut."""
    heard = {reply.reply_id: said(reply) is not None for reply in turn.conversation.replies}
    over, cut = turn.over_reply, turn.cut_reply
    notes: list[str] = []
    if over is not None and over == cut:
        notes.append(f"[said over your reply {over}, which it cut]")
    else:
        if over is not None:
            notes.append(f"[said over your reply {over}]")
        if cut is not None and heard.get(cut, False):
            notes.append(f"[it cut your reply {cut}]")
        elif cut is not None:
            notes.append(f"[it stopped your reply {cut} before any of it was heard]")
    return ChatMessage.user(" ".join([turn.words, *notes]))


def history(
    conversation: Conversation,
    *,
    exchanges: Mapping[TurnId, Sequence[ChatMessage]],
    notes: Mapping[TurnId, str],
    named: frozenset[ReplyId] = frozenset(),
) -> list[ChatMessage]:
    """The call so far as the model reads it (the module's docstring): `exchanges` holds the
    tool calls and results the talker kept of each past turn, `notes` its developer notes, and
    `named` the replies the turn answered now names."""
    turns = sorted(conversation.turns, key=lambda turn: turn.turn_id)
    messages: list[ChatMessage] = []
    at = 0

    def told(turn: PastTurn) -> None:
        text = _turn_text(turn)
        if text is not None:
            messages.append(ChatMessage.user(text))
        messages.extend(exchanges.get(turn.turn_id, ()))
        if turn.turn_id in notes:
            messages.append(ChatMessage.system(notes[turn.turn_id]))

    for reply in sorted(conversation.replies, key=lambda reply: reply.reply_id):
        while at < len(turns) and _before(turns[at], reply):
            told(turns[at])
            at += 1
        text = said(reply, named=reply.reply_id in named)
        if text is not None:
            messages.append(ChatMessage.assistant(text))
    for turn in turns[at:]:
        told(turn)
    return messages
