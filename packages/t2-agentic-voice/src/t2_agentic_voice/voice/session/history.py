"""What the caller heard, and only that (the design's 3.1; plan 005): the session's heard history.
Each of the caller's turns keeps its heard words (heard.py's `HeardWords`) and what became of it;
each of the agent's replies keeps its clauses, each `played` (its `ClausePlayed` came), `cut`
(playing at a stop or at the call's end, with the fraction of its audio played; a clause's words
are never split, Orpheus giving no word times) or `unplayed`. A repeat request says the last reply
again from it, the `CallReport` (a turn's `said`) and `AgentSpeechEnded(played_fraction)` read
it, and the talker takes its context from it (`conversation`: core/conversation.py's models, the
turns before the one it answers and every reply so far, so an unplayed clause never reaches the
model as said and a cut one reaches it marked cut, with its share); a turn whose reply was cut
before any clause played is marked (`rolled_back`), so the agent-led mode (D-050) can roll it
back. A confirmed action's job is handed the call so far from it, line by line (`lines`).

The session writes it: its turns (turn_book.py) and its replies (speaker.py), a talker's reply
clause by clause as it is written (`added`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from t2_agentic_voice.core.conversation import (
    ClauseFate,
    Conversation,
    ConversationLine,
    PastTurn,
    SaidClause,
    SaidReply,
    TurnFate,
)
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId

# What became of a clause and of a turn (`ClauseFate`, `TurnFate`) is core/conversation.py's,
# which the talker reads the call from.


@dataclass(frozen=True, kw_only=True)
class HeardClause:
    """One clause of a reply as the caller heard it: its text, what became of it, and the share
    of its audio that played (1 played, 0 unplayed, the share for a cut one)."""

    text: str
    fate: ClauseFate
    played_fraction: float


@dataclass(frozen=True, kw_only=True)
class HeardReply:
    """One of the agent's replies as the caller heard it: its number, the turn it answers (None
    for the greeting or a notice), and its clauses in order."""

    reply_id: ReplyId
    turn_id: TurnId | None
    clauses: tuple[HeardClause, ...]

    @property
    def heard(self) -> bool:
        """Whether any of it reached the caller: a clause played, or cut while it played."""
        return any(clause.fate != "unplayed" for clause in self.clauses)

    @property
    def played_fraction(self) -> float:
        """How much of it played, by its clauses' characters, a cut clause counting its share:
        1 when every clause played, or when it says nothing."""
        total = sum(len(clause.text) for clause in self.clauses)
        played = sum(len(clause.text) * clause.played_fraction for clause in self.clauses)
        return min(1.0, played / total) if total else 1.0

    @property
    def text(self) -> str:
        """What the caller heard of it: its clauses played or cut, one after another."""
        return " ".join(clause.text for clause in self.clauses if clause.fate != "unplayed")


@dataclass(frozen=True, kw_only=True)
class HeardTurn:
    """One of the caller's turns: its heard words ("" when nothing was heard), what became of
    it, and the reply that answers it, if any."""

    turn_id: TurnId
    words: str
    fate: TurnFate
    reply_id: ReplyId | None = None


class HeardHistory:
    """One call's heard history: each turn and each reply, as the module says, in order."""

    def __init__(self) -> None:
        self._turns: dict[TurnId, HeardTurn] = {}
        self._replies: dict[ReplyId, HeardReply] = {}

    def heard(self, words: HeardWords) -> None:
        """The caller's turn `words.turn_id` was heard: its words, its fate `pending`, or the
        one it already has (an overlap's verdict may come before the turn's own transcript)."""
        known = self._turns.get(words.turn_id)
        if known is None:
            known = HeardTurn(turn_id=words.turn_id, words="", fate="pending")
        self._turns[words.turn_id] = replace(known, words=words.text)

    def turn_ended(self, turn_id: TurnId, fate: TurnFate, *, reply_id: ReplyId | None) -> None:
        """What became of the caller's turn `turn_id`, and the reply that answers it; a turn
        never heard keeps no words."""
        known = self._turns.get(turn_id) or HeardTurn(turn_id=turn_id, words="", fate=fate)
        self._turns[turn_id] = replace(known, fate=fate, reply_id=reply_id)

    def asked(self, reply_id: ReplyId, turn_id: TurnId | None, texts: tuple[str, ...]) -> None:
        """The session asked for reply `reply_id`, its clauses' `texts` in order, each
        `unplayed` until it plays."""
        clauses = tuple(HeardClause(text=t, fate="unplayed", played_fraction=0.0) for t in texts)
        self._replies[reply_id] = HeardReply(reply_id=reply_id, turn_id=turn_id, clauses=clauses)

    def added(self, reply_id: ReplyId, text: str) -> None:
        """The session asked for the next clause of reply `reply_id`, still being written,
        `unplayed` until it plays."""
        reply = self._replies.get(reply_id)
        if reply is not None:
            clause = HeardClause(text=text, fate="unplayed", played_fraction=0.0)
            self._replies[reply_id] = replace(reply, clauses=(*reply.clauses, clause))

    def played(self, reply_id: ReplyId, clause: ClauseIndex) -> None:
        """The clause played whole (its `ClausePlayed` came)."""
        self._mark(reply_id, clause, "played", 1.0)

    def stopped(self, reply_id: ReplyId, *, playing: ClauseIndex | None, fraction: float) -> None:
        """A stop cut reply `reply_id`: the clause `playing` then (None when none played yet)
        is `cut`, `fraction` of its audio played; every clause after it stays `unplayed`."""
        if playing is not None:
            self._mark(reply_id, playing, "cut", min(1.0, max(0.0, fraction)))

    def reply(self, reply_id: ReplyId) -> HeardReply:
        """The reply `reply_id`; KeyError when it was never asked for."""
        return self._replies[reply_id]

    def turns(self) -> tuple[HeardTurn, ...]:
        """Every turn, in order."""
        return tuple(self._turns[turn_id] for turn_id in sorted(self._turns))

    def replies(self) -> tuple[HeardReply, ...]:
        """Every reply, in order."""
        return tuple(self._replies[reply_id] for reply_id in sorted(self._replies))

    def conversation(self, *, before: TurnId) -> Conversation:
        """The call as the talker reads it before the caller's turn `before`: every turn before
        it and every reply so far, each clause as the caller heard it."""
        turns = tuple(
            PastTurn(turn_id=t.turn_id, words=t.words, fate=t.fate, reply_id=t.reply_id)
            for t in self.turns()
            if t.turn_id < before
        )
        replies = tuple(
            SaidReply(
                reply_id=reply.reply_id,
                turn_id=reply.turn_id,
                clauses=tuple(
                    SaidClause(text=c.text, fate=c.fate, played_fraction=c.played_fraction)
                    for c in reply.clauses
                ),
            )
            for reply in self.replies()
        )
        return Conversation(turns=turns, replies=replies)

    def lines(self) -> tuple[ConversationLine, ...]:
        """The call so far as the caller heard it, in order, as an action may attach it (plan
        007's Q7): each turn's heard words, before the first reply that answers it or a later
        turn, and what the caller heard of each reply; nothing of a turn heard as nothing or a
        reply none of which played."""
        found: list[ConversationLine] = []
        turns = [turn for turn in self.turns() if turn.words]
        for reply in self.replies():
            while turns and reply.turn_id is not None and turns[0].turn_id <= reply.turn_id:
                found.append(ConversationLine(speaker="caller", text=turns.pop(0).words))
            if reply.text:
                found.append(ConversationLine(speaker="agent", text=reply.text))
        found += [ConversationLine(speaker="caller", text=turn.words) for turn in turns]
        return tuple(found)

    def last_reply(self) -> HeardReply | None:
        """The last reply asked for that the caller heard any of, the one playing (once a stop
        marked its clause cut) or the last played, which a repeat request says again; None
        before any."""
        heard = [reply for reply in self._replies.values() if reply.heard]
        return max(heard, key=lambda reply: reply.reply_id, default=None)

    def _mark(self, reply_id: ReplyId, index: ClauseIndex, fate: ClauseFate, share: float) -> None:
        reply = self._replies.get(reply_id)
        if reply is None or index >= len(reply.clauses):
            return
        clauses = list(reply.clauses)
        clauses[index] = replace(clauses[index], fate=fate, played_fraction=share)
        self._replies[reply_id] = replace(reply, clauses=tuple(clauses))
