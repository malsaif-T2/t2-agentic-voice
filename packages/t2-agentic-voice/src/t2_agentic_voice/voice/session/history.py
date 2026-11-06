"""What the caller heard, and only that (the design's 3.1; plan 005): the session's heard history.
Each of the caller's turns keeps its heard words (heard.py's `HeardWords`) and what became of it;
each of the agent's replies keeps its clauses, each `played` (its `ClausePlayed` came), `cut`
(playing at a stop or at the call's end, with the fraction of its audio played; a clause's words
are never split, Orpheus giving no word times) or `unplayed`. A repeat request says the last reply
again from it, the `CallReport` (a turn's `said`) and `AgentSpeechEnded(played_fraction)` read
it, and the talker will take its context from it; a turn whose reply was cut before any clause
played is marked (`rolled_back`), so the agent-led mode (D-050) can roll it back.

The session writes it: its turns (turn_book.py) and its replies (speaker.py).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from t2_agentic_voice.core.conversation import ClauseFate, TurnFate
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.heard import HeardWords

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
