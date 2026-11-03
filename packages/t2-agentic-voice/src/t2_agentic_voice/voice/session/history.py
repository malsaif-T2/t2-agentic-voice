"""What the caller heard, and only that (the design's 3.1; plan 005): the session's heard history.
Each of the caller's turns keeps its heard words (heard.py's `HeardWords`) and what became of it;
each of the agent's replies keeps its clauses, each `played` (its `ClausePlayed` came), `cut`
(playing at a stop, with the fraction of its audio played; a clause's words are never split,
Orpheus giving no word times) or `unplayed`. A repeat request says the last reply again from it,
the `CallReport` and `AgentSpeechEnded(played_fraction)` read it, and the talker will take its
context from it; a turn whose reply was cut before any clause played is marked, so the agent-led
mode (D-050) can roll it back.

Plan 005's Track B builds it; until then each method but the constructor raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.heard import HeardWords

# What became of a clause of a reply: it played whole, a stop cut it while it played, or it
# never played.
ClauseFate = Literal["played", "cut", "unplayed"]
# What became of one of the caller's turns: still being answered (`pending`); answered, its
# reply played whole; its reply `cut` after a clause played, or `rolled_back`, cut before any
# did; taken as a command (a stop, a pause, a repeat), not answered; an overlap after which the
# reply `went_on`; `dropped` by the drop rule; or `unfinished`, the call ended first.
TurnFate = Literal[
    "pending", "answered", "cut", "rolled_back", "command", "went_on", "dropped", "unfinished"
]


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
        """The caller's turn `words.turn_id` was heard: its words, its fate `pending`."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def turn_ended(self, turn_id: TurnId, fate: TurnFate, *, reply_id: ReplyId | None) -> None:
        """What became of the caller's turn `turn_id`, and the reply that answers it."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def asked(self, reply_id: ReplyId, turn_id: TurnId | None, texts: tuple[str, ...]) -> None:
        """The session asked for reply `reply_id`, its clauses' `texts` in order, each
        `unplayed` until it plays."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def played(self, reply_id: ReplyId, clause: ClauseIndex) -> None:
        """The clause played whole (its `ClausePlayed` came)."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def stopped(self, reply_id: ReplyId, *, playing: ClauseIndex | None, fraction: float) -> None:
        """A stop cut reply `reply_id`: the clause `playing` then (None when none played yet)
        is `cut`, `fraction` of its audio played; every clause after it stays `unplayed`."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def turns(self) -> tuple[HeardTurn, ...]:
        """Every turn, in order."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def replies(self) -> tuple[HeardReply, ...]:
        """Every reply, in order."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")

    def last_reply(self) -> HeardReply | None:
        """The last reply asked for, the one playing or the last played, which a repeat request
        says again; None before any."""
        raise NotImplementedError("the heard history is plan 005's Track B's to build")
