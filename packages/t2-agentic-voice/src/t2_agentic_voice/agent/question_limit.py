"""The question limit of one spoken reply (D-085; the owner's "Yes, add it", 2026-11-11): a reply
asks the caller at most `guard.questions_per_reply` questions (1 by default), and stops before
the next one.

- **A question** is a clause whose last character is a question mark, the Latin one or the
  Arabic one (domain/interruption_words.py's `QUESTION_MARKS`), once the spaces at its end and
  the quotes and closing brackets the clause splitter reads past (domain/text/clauses.py's
  `CLOSERS`) are taken off. So a question inside guillemets or quotes asks; a question mark
  inside the clause, or one followed by another mark ("?!"), does not.
- **One reply** (one turn, agent/turn.py, across its model requests) says the talker's clauses
  up to and including the last question it may ask. The next clause that asks one is dropped,
  and so is every clause after it: the reply stops there. The clauses between the questions are
  said. Each clause is judged as it comes, before the guard reads it, so nothing is held back,
  no text is changed and no model is asked.
- **Only what was said counts.** The limit reads the clauses said so far in the reply (those the
  guard passed, agent/speech_guard.py's `passed`), so a clause the guard blocked, or one the
  stray-script filter left with nothing to say, asks nothing. The session's own lines (a
  progress line, a notice, an action's read-back and its closing question, its outcome lines)
  never reach it, so they neither count nor stop a reply.
- **The count.** `QuestionLimit.unsaid` counts the clauses dropped. The turn gives it on
  `ReplyDone`, and `logged` writes `talker_reply_stopped` with the call, the turn, the reason
  and the count, never a word of the reply.

`asks` and `said_clauses` are pure: `said_clauses` runs one reply's clauses through one
`QuestionLimit`, as the turn does, for a check over stored replies.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from t2_agentic_voice.core.events import CallId, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.text.clauses import CLOSERS

_log = get_logger(__name__)
# Why a reply stopped, as its log line names it.
REASON = "question_limit"


def asks(clause: str) -> bool:
    """Whether `clause` asks the caller a question (the module's docstring)."""
    end = clause
    while end and (end[-1] in CLOSERS or end[-1].isspace()):
        end = end[:-1]
    return end[-1:] in QUESTION_MARKS


class QuestionLimit:
    """The question limit of one reply: `most`, the setting's value, None for no limit."""

    def __init__(self, most: int | None) -> None:
        self.most = most
        self.unsaid = 0  # the clauses dropped: the question past the limit, then all after it

    @property
    def stopped(self) -> bool:
        """Whether the reply has stopped, so nothing more of it is said."""
        return self.unsaid > 0

    def drops(self, clause: str, *, said: Sequence[str]) -> bool:
        """Whether the talker's next clause, `clause`, is dropped: the reply has stopped, or the
        clause asks a question and `said`, the reply's clauses said so far, already asked the
        most it may. Each clause dropped is counted."""
        if not self.stopped:
            if self.most is None or not asks(clause):
                return False
            if sum(asks(each) for each in said) < self.most:
                return False
        self.unsaid += 1
        return True

    def logged(self, *, call_id: CallId, turn_id: TurnId) -> None:
        """Log `talker_reply_stopped` when the reply stopped, by its counts alone."""
        if self.stopped:
            _log.info(
                "talker_reply_stopped",
                call_id=call_id,
                turn_id=turn_id,
                reason=REASON,
                unsaid_clauses=self.unsaid,
            )


def said_clauses(clauses: Iterable[str], *, most: int | None) -> tuple[str, ...]:
    """The clauses of one reply that are said under the limit `most`, in order, each judged as
    the turn judges it (every clause taken as one the guard would pass)."""
    limit, said = QuestionLimit(most), list[str]()
    for clause in clauses:
        if not limit.drops(clause, said=said):
            said.append(clause)
    return tuple(said)
