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
  in a note the prompt tells the model is never its to write. A turn that declined an action's
  read-back (`TalkerTurn.declined`) says so too, and how (`declined_note`): after a plain no
  the talker answers in its own words, and after a correction it may call the action again
  with the new draft (the owner's ruling, plan 007). The talker keeps that note beside the
  turn for the turns after it.
- **A turn split by a pause** reads as one (the owner's ruling of 2026-11-12, after the live call
  `LTLrFU`: "what tickets submitted with my", a pause, "email", answered as a question about
  email). When the caller's words stop the reply to their turn before it before any of that
  reply was heard (`cut_reply`), they go on with that turn, since the caller heard nothing in
  between: its words and theirs are one user message, in order (`continued`). The calls,
  results and notes the talker kept of the earlier turn stay where they came, before that
  message, so the model sees what it found for the first part and decides again on the whole
  (a correction's second part may need another search: run S's s05). Past turns read the same:
  a turn rolled back (`rolled_back`, its reply cut before any played) and the caller's next
  turn, no heard reply between them and the next no command, are one message.
- **A note the model copies** anyway, a reply's number or a cut clause's share, is taken out of
  what it writes before the clause splitter (`Unnoted`), so it is never spoken; only those two.
- **What only the talker knew** goes beside the heard history, in its place: the tool calls and
  results it kept of a past turn (agent/tool_calls.py's `Memory`), after that turn's words, or
  before them for a turn gone on with, whose words join the next turn's message, and the
  developer note of a clause the output guard held back from that turn's reply.
- **A request that offers no tool** holds each tool result as a system message and none of the
  calls that asked for them (`without_calls`).

The history holds two lists, the turns and the replies, each in order; they are told apart in
time by the turn each reply answers: a reply follows every turn up to the one it answers, and a
reply that answers none (the greeting, a notice) follows the turns its earlier replies
answered.

What a tool or an action's `validate` sees of the call is `call_context`'s: the verified caller,
the actions this call's record holds as plain values, and the caller's past actions read
through the action runner, the caller's own only (invariant 3).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise

from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.record import ActionRecord
from t2_agentic_voice.actions.tools import CallContext
from t2_agentic_voice.agent.prompt import CUT_MARK
from t2_agentic_voice.core.conversation import (
    Conversation,
    DeclinedAction,
    DeclineKind,
    PastTurn,
    SaidReply,
    TalkerTurn,
)
from t2_agentic_voice.core.events import CallId, ReplyId, TurnId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import ChatMessage

# The notes the model reads beside the caller's words and its own.
WENT_ON = "[said over your reply, which went on]"
BLOCKED = (
    "Note: the output guard held back a sentence of the reply to this turn, unspoken: it gave "
    "an ID-shaped number that no tool result or caller's words held. Never say such a number."
)
CLAIM_BLOCKED = (
    "Note: the output guard held back a sentence of the reply to this turn, unspoken: it said "
    "an action was done that no record or status result holds. Never say an action is done: "
    "the system says how it ended."
)
# How a turn that declined an action's read-back is told, by how it declined it.
DECLINED: Mapping[DeclineKind, str] = {
    "no": "[the caller said no to the read-back of {action}: nothing was done]",
    "correction": (
        "[the caller changed the read-back of {action}: nothing was done; call it again with "
        "the change]"
    ),
    # The owner's stop ruling; the call again after it, from the live call `_Hdmiy0vDE`
    # (2026-11-12), where a change said after the stop was taken for a note on a ticket.
    "stopped": (
        "[the caller stopped the read-back of {action}: nothing was done; ask what to change, "
        "keeping the draft, and once they say it, call {action} again with the change]"
    ),
    "unclear": "[the caller gave no clear answer to the read-back of {action}: nothing was done]",
}
# The notes `said` writes into the model's own messages: a reply's number, a cut clause's share
# (CUT_MARK). `Unnoted` takes them, and only them, out of what the model writes.
_NOTE = re.compile(r"\[(?:reply [0-9]+|cut: about [0-9]+% heard)\]")


def _beginnings(literal: str) -> str:
    """A pattern of every beginning of `literal`, the empty one included."""
    pattern = ""
    for character in reversed(literal):
        pattern = f"(?:{re.escape(character)}{pattern})?"
    return pattern


# A text that may still grow into a note: the beginning of one, up to its closing bracket.
_OPENING = re.compile(
    rf"\[(?:{_beginnings('reply ')}|reply [0-9]+|{_beginnings('cut: about ')}"
    rf"|cut: about [0-9]+{_beginnings('% heard')})"
)


class Unnoted:
    """The model's text as it streams, the history's notes taken out (`_NOTE`): `feed` gives
    each piece's text that holds none, holding back a tail that may begin one until it is whole
    or cannot be one; `close`, at the text's end, gives what is held."""

    def __init__(self) -> None:
        self._held = ""

    def feed(self, piece: str) -> str:
        """`piece`, with what was held before it, its notes taken out, less the tail held."""
        text = _NOTE.sub(" ", self._held + piece)
        start = text.rfind("[")
        opening = start >= 0 and _OPENING.fullmatch(text, start) is not None
        self._held = text[start:] if opening else ""
        return text[: len(text) - len(self._held)]

    def close(self) -> str:
        """What is held at the text's end, which never became a note."""
        held, self._held = self._held, ""
        return held


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


def declined_note(declined: DeclinedAction) -> str:
    """The note of an action's read-back the turn declined, by how (the module's docstring);
    it names the action, never the draft or the words."""
    return DECLINED[declined.kind].format(action=declined.action)


def _told(conversation: Conversation) -> list[PastTurn]:
    """The caller's past turns that reach the model, in order."""
    turns = sorted(conversation.turns, key=lambda turn: turn.turn_id)
    return [turn for turn in turns if _turn_text(turn) is not None]


def _goes_on(earlier: PastTurn, later: PastTurn, replies: Sequence[SaidReply]) -> bool:
    """Whether the caller's past turn `later` goes on with `earlier`, the turn told before it
    (the module's docstring): `earlier` rolled back, `later` no command, and no reply the caller
    heard between them."""
    if earlier.fate != "rolled_back" or later.fate == "command":
        return False
    return not any(
        said(reply) is not None and _before(earlier, reply) and not _before(later, reply)
        for reply in replies
    )


def continued(turn: TalkerTurn) -> tuple[PastTurn, ...]:
    """The caller's past turns the turn answered now goes on with, oldest first (the module's
    docstring): none unless its words stopped the reply to the caller's last turn before any of
    it was heard, and it was said over nothing heard; then that turn, and each before it that
    the next goes on with."""
    replies = {reply.reply_id: reply for reply in turn.conversation.replies}
    told = _told(turn.conversation)
    cut = None if turn.cut_reply is None else replies.get(turn.cut_reply)
    over = None if turn.over_reply is None else replies.get(turn.over_reply)
    if cut is None or not told or cut.turn_id != told[-1].turn_id or said(cut) is not None:
        return ()
    if turn.over_reply is not None and (over is None or said(over) is not None):
        return ()
    found = [told.pop()]
    while told and _goes_on(told[-1], found[0], turn.conversation.replies):
        found.insert(0, told.pop())
    return tuple(found)


def kept_of(
    turns: Sequence[PastTurn],
    *,
    exchanges: Mapping[TurnId, Sequence[ChatMessage]],
    notes: Mapping[TurnId, str],
) -> list[ChatMessage]:
    """The calls, results and developer notes the talker kept of `turns`, in order."""
    kept: list[ChatMessage] = []
    for turn in turns:
        kept.extend(exchanges.get(turn.turn_id, ()))
        if turn.turn_id in notes:
            kept.append(ChatMessage.system(notes[turn.turn_id]))
    return kept


def turn_message(turn: TalkerTurn) -> ChatMessage:
    """The turn answered now, its words whole, after those of the turns it goes on with
    (`continued`), then what it was said over and what it cut, and the read-back it declined."""
    heard = {reply.reply_id: said(reply) is not None for reply in turn.conversation.replies}
    joined = [past.words for past in continued(turn)]
    over, cut = turn.over_reply, turn.cut_reply
    notes: list[str] = []
    if over is not None and over == cut:
        notes.append(f"[said over your reply {over}, which it cut]")
    else:
        if over is not None:
            notes.append(f"[said over your reply {over}]")
        if cut is not None and heard.get(cut, False):
            notes.append(f"[it cut your reply {cut}]")
        elif cut is not None and not joined:
            notes.append(f"[it stopped your reply {cut} before any of it was heard]")
    if turn.declined is not None:
        notes.append(declined_note(turn.declined))
    return ChatMessage.user(" ".join([*joined, turn.words, *notes]))


def without_calls(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """`messages` for a request that offers no tool: each result kept, framed as it was, and the
    calls that asked for them dropped. A model that can read its own calls sometimes writes
    another, which Groq refuses when the request offers none (run K, D-075)."""
    kept: list[ChatMessage] = []
    for message in messages:
        if message.role == "tool":
            kept.append(ChatMessage.system(message.content))
        elif not message.tool_calls:
            kept.append(message)
        elif message.content:
            kept.append(ChatMessage.assistant(message.content))
    return kept


def call_context(
    *,
    caller: Caller,
    call_id: CallId,
    language: LanguageTag,
    actions: ActionRunner | None,
    record: ActionRecord | None,
) -> CallContext:
    """What a tool or an action's `validate` sees of the call (the module's docstring): the
    record's entries as plain values, and `past_actions` read through `actions`, when the agent
    has any."""
    ctx = CallContext(
        caller=caller,
        call_id=call_id,
        language=language,
        record=() if record is None else record.view(),
    )
    return ctx if actions is None else ctx.reading_past(actions.past)


def history(
    conversation: Conversation,
    *,
    exchanges: Mapping[TurnId, Sequence[ChatMessage]],
    notes: Mapping[TurnId, str],
    named: frozenset[ReplyId] = frozenset(),
    continued: Sequence[PastTurn] = (),
) -> list[ChatMessage]:
    """The call so far as the model reads it (the module's docstring): `exchanges` holds the
    tool calls and results the talker kept of each past turn, `notes` its developer notes,
    `named` the replies the turn answered now names, and `continued` the turns it goes on with,
    whose words it says itself (`turn_message`)."""
    turns = sorted(conversation.turns, key=lambda turn: turn.turn_id)
    replies = sorted(conversation.replies, key=lambda reply: reply.reply_id)
    spoken = _told(conversation)
    later = {turn.turn_id: after for turn, after in pairwise(spoken)}
    tail = {turn.turn_id for turn in continued}
    messages: list[ChatMessage] = []
    words: list[str] = []  # the words of the turns told so far that the next goes on with
    at = 0

    def told(turn: PastTurn) -> None:
        text, mine = _turn_text(turn), kept_of([turn], exchanges=exchanges, notes=notes)
        if text is not None and turn.turn_id not in tail:
            words.append(text)
            after = later.get(turn.turn_id)
            if after is None or after.turn_id in tail or not _goes_on(turn, after, replies):
                messages.append(ChatMessage.user(" ".join(words)))
                words.clear()
        messages.extend(mine)  # in the order they came: a turn gone on with, before its words

    for reply in replies:
        while at < len(turns) and _before(turns[at], reply):
            told(turns[at])
            at += 1
        text = said(reply, named=reply.reply_id in named)
        if text is not None:
            messages.append(ChatMessage.assistant(text))
    for turn in turns[at:]:
        told(turn)
    return messages
