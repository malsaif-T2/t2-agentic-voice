"""When the parts of an action's read-back played, read from the transport's `ClausePlayed`
reports, never the browser's `playback` message (docs/SECURITY.md, invariant 1), and what that says
of the caller's speech (`ReadBackTimes`, the base of read_back.py's `Confirming`). Apart from
read_back.py so each stays within the size a module may have (ARCH-SIZE).

- **The receipt**, which only read_back.py builds (`Confirming.receipt`), when the yes rule is
  called, so a verdict landing late can still deny it: it stands for a summary that played whole,
  every clause of it played, none cut short, each with audio (`whole`; a stop that cut the reply
  after its summary changes none of that); no overlap begun over the summary undecided; and the
  turn's speech begun once its last clause played. Its `question_ended_at` is the closing
  question's last `ClausePlayed`, None until every clause of the question has played so; its
  `summary_began_at` when the summary could first be heard (`began`).
- **When a part could first be heard** (`began`): its first audio queued, or, after another
  clause of the same reply (the talker's own words, a progress line), once that clause played,
  whichever is later; None until then. The transport queues a clause's audio once the one before
  it is made, while that one still plays, so the summary is heard only once the clause before it
  ends: words begun before then are never words over the summary (D-108).
- **Over a part** (`over`): speech begun before its last clause played, or with none played.
- **What was still heard** (`heard`, D-082's echo rail): speech begun over one of some replies,
  each playing or within its tail after it ended (playback.py's `Reply.over`); True with no time,
  or for a reply the session no longer holds: the read-back's (`over_read_back`), or a line's
  that asked it again (`over_follow_up`), so the yes rule's echo rail keeps their lines when the
  session cannot tell.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from t2_agentic_voice.core.events import ReplyId
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.voice.protocol import ClauseIndex
from t2_agentic_voice.voice.session.playback import Playback, Reply

# Whether an overlap of a reply, its speech begun before a time, is still undecided (overlap.py's
# `Overlaps.undecided`).
Undecided = Callable[[ReplyId, float], bool]


@dataclass(frozen=True, kw_only=True)
class ReadBack:
    """One draft read back: its `plan`, the reply that says it, and the indexes of its clauses
    there, the summary's and the closing question's."""

    plan: ReadBackPlan
    reply_id: ReplyId
    summary: tuple[ClauseIndex, ...]
    question: tuple[ClauseIndex, ...]


def whole(reply: Reply | None, indexes: tuple[ClauseIndex, ...]) -> float | None:
    """When the last of `indexes`, clauses of `reply`, played, once every one of them played
    whole with audio; None until then, or when one never will."""
    if reply is None or not indexes:
        return None
    clauses = [reply.clauses[index] for index in indexes if index < len(reply.clauses)]
    if len(clauses) != len(indexes):
        return None
    if not all(c.played and not c.cut_short and c.audio_s > 0 for c in clauses):
        return None
    return max(c.played_at or 0.0 for c in clauses)


def began(reply: Reply | None, indexes: tuple[ClauseIndex, ...]) -> float | None:
    """When the clauses `indexes` of `reply` could first be heard (the module's docstring); None
    until then."""
    if reply is None or not indexes or indexes[0] >= len(reply.clauses):
        return None
    first = indexes[0]
    queued = reply.clauses[first].queued_at
    if queued is None or first == 0:
        return queued
    before = reply.clauses[first - 1].played_at  # None until it played whole, or if it failed
    return None if before is None else max(queued, before)


def over(reply: Reply | None, indexes: tuple[ClauseIndex, ...], speech_at: float) -> bool:
    """Whether speech begun at `speech_at` began before the last of `indexes`, clauses of
    `reply`, played."""
    last = None if reply is None else reply.clauses[indexes[-1]]
    ended = None if last is None or not last.played else last.played_at
    return ended is None or speech_at < ended


def heard(playback: Playback, speech_at: float | None, reply_ids: Collection[ReplyId]) -> bool:
    """Whether speech begun at `speech_at` began over one of `reply_ids`, its tail included;
    True with no time, or for a reply the session no longer holds."""
    if speech_at is None:
        return True
    for reply_id in reply_ids:
        reply = playback.reply(reply_id)
        if reply is None or reply.over(speech_at):
            return True
    return False


class ReadBackTimes:
    """What the current read-back's times say of speech begun at a time (the module's
    docstring): the base of read_back.py's `Confirming`, which keeps the current read-back
    (`read_back`), the replies `_playback` keeps and the lines that asked it again
    (`_follow_ups`)."""

    read_back: ReadBack | None
    _playback: Playback
    _follow_ups: set[ReplyId]

    def answering(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` answers the current read-back: it began once
        the read-back's summary had played its last clause (yes_turns.py's)."""
        read_back = self.read_back
        if read_back is None or speech_at is None:
            return False
        return not over(self._playback.reply(read_back.reply_id), read_back.summary, speech_at)

    def summary_began_at(self) -> float | None:
        """When the current read-back's summary could first be heard (`began`); None before,
        or with none current."""
        read_back = self.read_back
        if read_back is None:
            return None
        return began(self._playback.reply(read_back.reply_id), read_back.summary)

    def over_read_back(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` began while the current read-back was still
        heard (`heard`, the drop rule's window, the transport's reports); True when the session
        cannot tell, so the yes rule's echo rail keeps its lines (domain/yes_rule.py's
        `judged`)."""
        read_back = self.read_back
        return read_back is None or heard(self._playback, speech_at, (read_back.reply_id,))

    def over_follow_up(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` began while a line that asked the current
        read-back again was still heard: from its reply's first audio queued to the end of its
        tail after it ended, as `over_read_back` reads the read-back's; True when the session
        cannot tell, so the echo rail keeps that line."""
        return heard(self._playback, speech_at, self._follow_ups)
