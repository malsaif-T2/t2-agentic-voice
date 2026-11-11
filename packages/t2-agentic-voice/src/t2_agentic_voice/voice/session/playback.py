"""The agent's replies as they play, for one call's session (voice/session/call.py): which the
session has asked for, which are playing, how much of each played, and when each began and ended
(`Playback`; voice/session/io.py's replies, the drop rule and the stop path). The `Speaker`, which
asks for each reply clause by clause and ends each, is speaker.py's.

A reply plays from its first clause's first audio (`ClauseQueued`) to its end: its last clause
played or failed, or a stop or the call's end that dropped what was left. The drop rule, the
overlaps and the yes rule's echo rail (read_back.py) read those times: a turn whose speech began
while a reply played, or within `DROP_AFTER_S` after one ended, is over it (`Reply.over`,
`Playback.over`); a reply the caller's own `stop` ended has no such tail, since nothing of it
plays on to echo (TD-060). Its clauses tell which one plays now
(`playing`), and which played lately, whose words the agent's own voice heard back would say
(`heard_since`).

The talker's reply is written while it plays (plan 006): it is opened with no clause (`open`),
each clause added as it comes (`add`), and closed once its work is done (`close`); until then it
does not end when its clauses have all played, and while it has nothing left to play it is
thinking, not speaking. An action's read-back (plan 007) is clauses of such a reply, each marked
with its `part`, the summary's or the closing question's, so whoever reads the reply can tell
them apart (read_back.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing_tts import ReplyNumbers
from t2_agentic_voice.domain.declaration import NoticeKind
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.echo import Line
from t2_agentic_voice.voice.session.session_events import (
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    Synthesizing,
)

# How long after a reply ends a turn's speech still counts as the agent's own voice, leaked past
# the browser's echo cancellation (plan 003's decision log): seconds.
DROP_AFTER_S = 0.3
# What a reply is: the greeting (reply 0), a turn's echo, a spoken notice, the last reply said
# again at the caller's request, or the talker's answer, spoken while it is written (plan 006).
ReplyKind = Literal["greeting", "echo", "notice", "repeat", "answer"]
# Which part of an action's read-back a clause says: the summary, which the receipt covers, or
# the closing question.
ReadBackPart = Literal["summary", "question"]


@dataclass(kw_only=True)
class Clause:
    """One clause of a reply as it plays: its caption, the text its request sends (`sent`, as
    the speaking rules and the pronunciation map said it, which a reply said again sends) and
    its characters (none for a cached phrase), whether it is a fixed phrase (`cached`) or a take
    the clause cache held (`held`, set once its audio is queued: a cache hit, never a phrase),
    whether it is a progress line (`progress`, timed apart), the language it is spoken in, the
    read-back's part it says (`part`, None for any other clause), and what came of it
    (`played_at`, when its `ClausePlayed` came, with the seconds of audio it reported)."""

    caption: str
    characters: int
    cached: bool
    sent: str = ""
    held: bool = False
    progress: bool = False
    language: LanguageTag | None = None
    part: ReadBackPart | None = None
    requested_at: float | None = None
    queued_at: float | None = None
    played: bool = False
    played_at: float | None = None
    done: bool = False
    chunks: int = 0
    audio_s: float = 0.0
    cut_short: bool = False


@dataclass(kw_only=True)
class Reply:
    """One of the agent's replies: its number, what it is, the caller's turn it answers (None
    for the greeting or a notice), the notice it speaks, its clauses, when it began and ended
    playing (`ended_at` set however it ended), whether a clause failed and the caller was told
    of it (`told`: one `error` notice a reply), whether a stop dropped it (`stopped`), or a stop
    or the call's end (`cut`), how long after its end speech still counts as over it (`tail_s`:
    none after the caller's own `stop`), and whether it is still being written (`open`: the
    talker's, until closed)."""

    reply_id: ReplyId
    kind: ReplyKind
    turn_id: TurnId | None = None
    notice: NoticeKind | None = None
    clauses: list[Clause] = field(default_factory=list)
    started_at: float | None = None
    ended_at: float | None = None
    failed: bool = False
    told: bool = False
    to_tell: bool = False  # a clause failed: the caller is told when the reply ends
    stopped: bool = False
    cut: bool = False
    tail_s: float = DROP_AFTER_S
    open: bool = False

    @property
    def sounding(self) -> bool:
        """Whether it plays now: its first audio queued, and a clause asked for still to play
        or it is closed (a reply still being written with nothing left to play is thinking)."""
        if self.started_at is None:
            return False
        return not self.open or any(not clause.done for clause in self.clauses)

    @property
    def text(self) -> str:
        """What the reply was to say: its clauses' captions, one after another."""
        return " ".join(clause.caption for clause in self.clauses)

    @property
    def first_audio_s(self) -> float | None:
        """From its first request to that request's first audio: none when no request's audio
        came."""
        for clause in self.clauses:
            if clause.requested_at is not None and clause.queued_at is not None:
                return max(0.0, clause.queued_at - clause.requested_at)
        return None

    def over(self, speech_at: float) -> bool:
        """Whether speech begun at `speech_at` began over it, its voice still heard: while it
        played, from its first audio queued, or within its tail after it ended (`tail_s`)."""
        if self.started_at is None or self.started_at > speech_at:
            return False
        return self.ended_at is None or speech_at <= self.ended_at + self.tail_s

    def numbers(self) -> ReplyNumbers:
        """What it took, as its text-to-speech span records it: the requests that went (their
        characters), the chunks played, the phrases and held takes played from the caches."""
        asked = [clause for clause in self.clauses if clause.requested_at is not None]
        first = self.first_audio_s
        return ReplyNumbers(
            characters=sum(clause.characters for clause in asked),
            chunks=sum(clause.chunks for clause in self.clauses),
            requests=len(asked),
            cache_hits=sum(clause.cached or clause.held for clause in self.clauses),
            first_audio_ms=None if first is None else first * 1000,
            cut_short=any(clause.cut_short for clause in self.clauses),
        )


class Playback:
    """Every reply of one call, by its number, the next numbered from 0."""

    def __init__(self) -> None:
        self._replies: dict[ReplyId, Reply] = {}

    @property
    def next_id(self) -> ReplyId:
        """The number the next reply takes."""
        return len(self._replies)

    def ask(
        self,
        kind: ReplyKind,
        lines: list[Line],
        *,
        turn_id: TurnId | None = None,
        notice: NoticeKind | None = None,
    ) -> Reply:
        """Keep the reply `lines` say, numbered `next_id`: each a cached phrase, or a request of
        its text's characters."""
        clauses = [_clause(line) for line in lines]
        reply = Reply(
            reply_id=self.next_id, kind=kind, turn_id=turn_id, notice=notice, clauses=clauses
        )
        self._replies[reply.reply_id] = reply
        return reply

    def open(self, kind: ReplyKind, *, turn_id: TurnId | None) -> Reply:
        """Keep a reply still being written, numbered `next_id`, with no clause yet."""
        reply = Reply(reply_id=self.next_id, kind=kind, turn_id=turn_id, open=True)
        self._replies[reply.reply_id] = reply
        return reply

    def add(
        self, reply: Reply, line: Line, *, progress: bool = False, part: ReadBackPart | None = None
    ) -> Clause:
        """Add the clause `line` says to the open `reply`, at its next index."""
        clause = _clause(line, progress=progress, part=part)
        reply.clauses.append(clause)
        return clause

    def close(self, reply: Reply, at: float) -> bool:
        """`reply` is written whole: whether it ends at `at`, every clause of it done (or none
        asked for)."""
        reply.open = False
        if reply.ended_at is None and all(clause.done for clause in reply.clauses):
            reply.ended_at = at
            return True
        return False

    def reply(self, reply_id: ReplyId) -> Reply | None:
        return self._replies.get(reply_id)

    def clause(self, reply_id: ReplyId, index: ClauseIndex) -> tuple[Reply, Clause] | None:
        """The reply and its clause an event names, while the reply plays; None for any other."""
        reply = self._replies.get(reply_id)
        if reply is None or reply.ended_at is not None or index >= len(reply.clauses):
            return None
        return reply, reply.clauses[index]

    def requested(self, event: Synthesizing) -> Clause | None:
        """The clause whose request went, which `event` reports, its reply ended or not: the
        report of a request that went before the call's end still comes after it."""
        reply = self._replies.get(event.reply_id)
        if reply is None or event.clause >= len(reply.clauses):
            return None
        clause = reply.clauses[event.clause]
        clause.requested_at = event.at
        return clause

    def queued(self, event: ClauseQueued) -> tuple[Reply, Clause] | None:
        """The clause whose first audio `event` reports queued; its reply begins playing."""
        found = self.clause(event.reply_id, event.clause)
        if found is not None:
            reply, clause = found
            clause.queued_at, clause.held = event.at, event.held
            if reply.started_at is None:
                reply.started_at = event.at
        return found

    def done(self, event: ClausePlayed | ClauseFailed) -> tuple[Reply, Clause] | None:
        """The clause `event` reports played whole or failed; its reply ends with its last."""
        found = self.clause(event.reply_id, event.clause)
        if found is None:
            return None
        reply, clause = found
        clause.done = True
        if isinstance(event, ClausePlayed):
            clause.played, clause.played_at = True, event.at
            clause.chunks, clause.cut_short = event.chunks, event.cut_short
            clause.audio_s = event.audio_s
        else:
            reply.failed = True
        if not reply.open and all(each.done for each in reply.clauses):
            reply.ended_at = event.at
        return found

    def in_progress(self) -> list[Reply]:
        """The replies asked for that have not ended, oldest first."""
        return [reply for reply in self._replies.values() if reply.ended_at is None]

    def drop(self, at: float, *, tail: bool = True) -> list[Reply]:
        """End at `at` every reply asked for that has not ended, as a stop or the call's end
        drops them, with no tail after it unless `tail` (the caller's own `stop` leaves none);
        the replies dropped, oldest first."""
        dropped = self.in_progress()
        for reply in dropped:
            reply.ended_at, reply.cut = at, True
            if not tail:
                reply.tail_s = 0.0
        return dropped

    def playing(self) -> tuple[Reply, ClauseIndex] | None:
        """The clause playing now, and its reply: the first not yet done of the oldest reply
        playing, once its first audio was queued; None when no clause plays (clauses play in
        the order they were asked for)."""
        for reply in self.in_progress():
            for index, clause in enumerate(reply.clauses):
                if not clause.done:
                    return (reply, index) if clause.queued_at is not None else None
        return None

    def heard_since(self, since: float) -> tuple[str, ...]:
        """The captions of the clauses that played at or after `since`, in order, then the one
        playing now: what the agent's own voice, heard back through the caller's microphone,
        would say."""
        played = [
            clause
            for reply in self._replies.values()
            for clause in reply.clauses
            if clause.played_at is not None and clause.played_at >= since
        ]
        texts = [clause.caption for clause in sorted(played, key=lambda c: c.played_at or 0.0)]
        now = self.playing()
        if now is not None:
            texts.append(now[0].clauses[now[1]].caption)
        return tuple(texts)

    @property
    def speaking(self) -> bool:
        """Whether a reply is playing (`Reply.sounding`)."""
        return any(reply.sounding for reply in self.in_progress())

    @property
    def waiting(self) -> bool:
        """Whether a reply asked for has no audio queued yet, or is still being written with
        nothing left to play."""
        return any(not reply.sounding for reply in self.in_progress())

    def over(self, speech_at: float) -> Reply | None:
        """The newest reply that speech begun at `speech_at` began over: one playing then, or
        that had ended within its tail before it (`DROP_AFTER_S`, none after the caller's own
        `stop`); None when it began over none (the drop rule and the overlaps)."""
        found = None
        for reply in self._replies.values():
            if reply.over(speech_at):
                found = reply
        return found


def _clause(line: Line, *, progress: bool = False, part: ReadBackPart | None = None) -> Clause:
    """The clause `line` says: a cached phrase, or a request of its text's characters, in the
    language it is spoken in."""
    cached = line.speak.audio is not None
    return Clause(
        caption=line.caption,
        characters=0 if cached else len(line.speak.text),
        cached=cached,
        sent=line.speak.text,
        progress=progress,
        language=line.speak.language,
        part=part,
    )
