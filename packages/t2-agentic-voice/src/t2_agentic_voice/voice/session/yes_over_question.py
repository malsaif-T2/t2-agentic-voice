"""A yes said over the question that ends a reply (D-116, the owner's ruling of 2026-11-17, "Any
yes books"), for interrupter.py, only under `interruptions.answer_yes_over_question`, off by
default (GP-18): any agent's yes/no question with no read-back, the lean flight agent's "Shall I
book it?" among them.

- **Held** (`hold`). A turn the agent's voice went on over (a go-on overlap: interrupter.py's
  `_hand_over`), that is not the read-back's yes rule's (read_back_heard.py's `takes` is asked
  first, and a yes held over a read-back keeps its own path: held_yes.py), whose own words are a
  yes (domain/yes_kinds.py's `question_yes`: a yes or a send word among only yes words, send
  words and fillers, by the lists of the language they were heard in, else the call's, the
  `words` group's added, never the agent's own lines that played as the speech began heard
  back), and whose verdict was no echo of the agent's own words (`own_words`), is held,
  unsettled, until the reply it began over ends. Its `Interrupted` of kind `false` and the
  voice's flow are as for any go-on overlap.
- **Dropped** (`heard`, told every other turn's own transcript), in the order said, as
  held_yes.py drops one: any other words whose speech began after a held yes let it go (`why`
  `words`), settled as a go-on overlap: a turn the voice went on over whose words are no yes,
  fillers or listening sounds ("Yes." then "No."), one that stopped the reply or was answered,
  a command, one said once the agent was silent, or one whose transcript failed. A yes begun
  before words that let one go is never held. Another yes, fillers or listening sounds keep it,
  and so does a turn in which nothing was heard.
- **Answered** (`flush`, after each step of the session's: interrupter.py's). Once that reply
  has ended, and its tail (playback.py's `DROP_AFTER_S`), `turns.vad_start_ms` and held_yes.py's
  `LAG_S` more have passed (a turn begun over the reply or its tail opens that late, its start
  backdated; a step of the session's then, `_wake`), with no other words on the way (`quiet`,
  which interrupter.py tells: no turn open or awaiting its words, no overlap undecided), a held
  turn is answered as the caller's next turn, its own words handed to the talker like any
  turn's, when all of these hold (`over_question`): the reply was not stopped or cut, and its
  last clause played; that clause is a question (its caption ends with a question mark); no
  clause of the reply is a read-back's (playback.py's `part`); and the turn's speech began once
  that clause could first be heard (read_back_times.py's `began`: every clause before it
  played), while it played or within its tail. One turn a reply at most, the first said (never
  twice); every other held turn is let go, settled as a go-on overlap (its fate `went_on`), once
  its reply has ended. Each is a log line, with no word of the call: `question_yes_held`,
  `question_yes_answered` and `question_yes_let_go` (`why`: `stopped`, the reply stopped or
  cut; `not_over`, no question ends it or the speech began before it; `second`, one was
  answered already; `words`, the module's Dropped).
- **What an app sees**: the turn's `UserTurnEnded` goes out when its words are heard, so before
  the reply's `AgentSpeechEnded` when they come while it plays; its `reply_played` holds what of
  the reply had played when its speech began (reply_played.py).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from t2_agentic_voice.core.events import ReplyId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.domain.interruption_words import QUESTION_MARKS
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.words import heard_code
from t2_agentic_voice.domain.yes_kinds import question_yes
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words, covered
from t2_agentic_voice.voice.session.held_yes import LAG_S
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.overlap import call_words
from t2_agentic_voice.voice.session.overlap_follow import Answer, Follows
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.read_back_times import began
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class Held:
    """A turn held until `reply_id`, the reply it began over, ends: its own words and
    transcript."""

    turn: TurnLog
    heard: HeardWords
    event: Transcribed
    reply_id: ReplyId


def over_question(reply: Reply, speech_at: float | None) -> bool:
    """Whether speech begun at `speech_at` began over the question that ends `reply`, which has
    ended (the module's Answered)."""
    if speech_at is None or not reply.clauses or reply.cut or reply.stopped:
        return False
    last = len(reply.clauses) - 1
    question = reply.clauses[last]
    if not question.played or any(clause.part is not None for clause in reply.clauses):
        return False
    if not question.caption.rstrip().endswith(QUESTION_MARKS):
        return False
    heard_at = began(reply, (last,))
    return heard_at is not None and heard_at <= speech_at and reply.over(speech_at)


class YesOverQuestion:
    """One call's yeses held over a reply's closing question (the module's docstring), the
    replies read from `playback`, the turns `turns` keeps settled, a held turn answered by
    `answer` (`pending` again first, by `follows`), and a step due later run as `guarded` runs
    it, the session's `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        playback: Playback,
        *,
        turns: TurnBook,
        follows: Follows,
        answer: Answer,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
    ) -> None:
        self._setup, self._playback, self._turns = setup, playback, turns
        self._follows, self._answer = follows, answer
        self._guarded, self._sync, self._clock = guarded, sync, setup.clock
        self._on = setup.settings.interruptions.answer_yes_over_question
        self._wait_s = setup.settings.turns.vad_start_ms / 1000 + LAG_S
        self._held: list[Held] = []
        self._answered: set[ReplyId] = set()
        self._after: float | None = None  # when the latest words that let a yes go began
        self._waking: asyncio.Task[None] | None = None

    def hold(
        self,
        turn: TurnLog,
        heard: HeardWords | None,
        event: Transcribed,
        verdict: Verdict,
        played: Sequence[str],
    ) -> bool:
        """Whether `turn`, its overlap's `verdict` to go on, its words `heard` in `event` as
        the agent's lines `played` were heard, is held until its reply ends (the module's
        Held); a yes begun before words that let one go is not (the module's Dropped)."""
        reply_id = turn.over_reply
        if not self._on or heard is None or reply_id is None or event.failure is not None:
            return False
        words = self._words(heard)
        if verdict.reason == "own_words" or not question_yes(heard.text, words, played=played):
            return False
        later, speech_at = self._after, heard.speech_at
        if later is not None and (speech_at is None or speech_at < later):
            self._line("question_yes_let_go", turn, why="words")
            return False
        self._held.append(Held(turn=turn, heard=heard, event=event, reply_id=reply_id))
        self._line("question_yes_held", turn)
        return True

    def went_on(
        self,
        turn: TurnLog,
        heard: HeardWords | None,
        event: Transcribed,
        verdict: Verdict,
        played: Sequence[str],
    ) -> None:
        """`turn`, a go-on overlap's (`verdict`) that is not the read-back's yes rule's, its words
        `heard` in `event` as the agent's lines `played` were heard: held (`hold`), or settled,
        its words told first (`heard`)."""
        if not self.hold(turn, heard, event, verdict, played):
            self.heard(turn, heard, event, answered=False)
            self._turns.settle(turn)

    def heard(
        self, turn: TurnLog, heard: HeardWords | None, event: Transcribed, *, answered: bool
    ) -> None:
        """`turn`'s words `heard` in `event`, not held: each held turn they let go settled (the
        module's Dropped); `answered` for a turn the session takes (answered, a command, or one
        that stopped the reply), which lets one go whatever its words."""
        if not self._on or (heard is None and event.failure is None):
            return  # off, or nothing was heard
        if heard is not None and not answered and self._keeps(heard):
            return
        speech_at = turn.speech_at if heard is None else heard.speech_at
        if speech_at is None:
            return
        self._after = speech_at if self._after is None else max(self._after, speech_at)
        kept: list[Held] = []
        for held in self._held:
            began_at = held.heard.speech_at
            if began_at is not None and began_at >= speech_at:
                kept.append(held)  # said after these words: they say nothing of it
                continue
            self._line("question_yes_let_go", held.turn, why="words")
            self._turns.settle(held.turn)
        self._held = kept

    async def flush(self, at: float, *, quiet: bool) -> None:
        """At `at`, each held turn whose reply has ended answered once its wait has passed and
        the call is `quiet`, at most one a reply, or let go, settled (the module's Answered);
        each held turn once."""
        answer: list[Held] = []
        kept: list[Held] = []
        waiting: set[ReplyId] = set()
        for held in sorted(self._held, key=lambda each: each.turn.turn_id):
            reply = self._playback.reply(held.reply_id)
            if held.reply_id in waiting or (reply is not None and reply.ended_at is None):
                kept.append(held)
                continue
            why = self._why_not(held, reply)
            if why is None and reply is not None and not self._ready(reply, at, quiet=quiet):
                waiting.add(held.reply_id)
                kept.append(held)
            elif why is None:
                self._answered.add(held.reply_id)
                answer.append(held)
                self._line("question_yes_answered", held.turn)
            else:
                self._line("question_yes_let_go", held.turn, why=why)
                self._turns.settle(held.turn)
        self._held = kept
        for held in answer:
            turn = self._follows.pending(held.turn)
            await self._answer(turn, held.heard, replace(held.event, at=at))

    def end(self) -> None:
        """The call ended: nothing held is answered."""
        self._held = []
        if self._waking is not None:
            self._waking.cancel()
            self._waking = None

    def _ready(self, reply: Reply, at: float, *, quiet: bool) -> bool:
        """Whether a yes held over `reply`, which ended, may be answered at `at`: its wait has
        passed (a step of the session's woken then when not), and the call is `quiet`."""
        due = (at if reply.ended_at is None else reply.ended_at) + reply.tail_s + self._wait_s
        if at < due:
            self._wake(due - at)
            return False
        return quiet

    def _wake(self, wait: float) -> None:
        """A step of the session's in `wait` seconds (`sync`, which answers a yes held then
        due), one at a time."""
        if self._waking is None:
            self._waking = asyncio.create_task(self._woken(wait), name="question-yes-due")

    async def _woken(self, wait: float) -> None:
        await self._clock.sleep(wait)
        self._waking = None
        await self._guarded("question_yes_due", self._sync)

    def _why_not(self, held: Held, reply: Reply | None) -> str | None:
        """Why `held`, its reply `reply` ended, is let go; None when it is answered."""
        if reply is None or reply.cut or reply.stopped:
            return "stopped"
        if held.reply_id in self._answered:
            return "second"
        return None if over_question(reply, held.heard.speech_at) else "not_over"

    def _keeps(self, heard: HeardWords) -> bool:
        """Whether `heard`, words the voice went on over, keep a held yes: another yes, or
        fillers and listening sounds alone (the module's Dropped)."""
        words = self._words(heard)
        if question_yes(heard.text, words, played=()):
            return True
        return covered(heard.text, (*words.fillers, *call_words(self._setup).backchannel))

    def _words(self, heard: HeardWords) -> ConsentWords:
        """The yes rule's lists in the language `heard` was heard in, else the call's, with the
        `words` settings group's additions."""
        code = heard_code(heard.language) or self._setup.now.primary
        added = self._setup.settings.words
        return consent_words(
            code, added_yes=added.yes.get(code, ()), added_send=added.send.get(code, ())
        )

    def _line(self, line: str, turn: TurnLog, **fields: str) -> None:
        _log.info(line, call_id=self._setup.call_id, turn_id=turn.turn_id, **fields)
