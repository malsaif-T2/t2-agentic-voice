"""A yes held over an action's read-back (D-108, the owner's ruling of 2026-11-17, "Any yes
books"; docs/SECURITY.md, invariant 1), for yes_turns.py, only under
`interruptions.yes_over_read_back`, off by default (GP-18).

- **Held** (`over_summary`). A turn whose speech began over the current read-back's summary,
  once it could first be heard (read_back_times.py's `began`), and that the agent's voice went
  on over (read_back_heard.py's `takes` and `plays_on`) comes here with its own heard words.
  Words the yes rule's lists read as a yes held on it (domain/yes_kinds.py's `held_yes`: a yes
  or a send word among only yes words, send words and fillers, khalas among them) are held on
  that read-back, with the turn and when its speech began; a second yes keeps the first held,
  and so do fillers or listening sounds alone. For an agent that asks, words the lists leave
  unplaced (read_back_heard.py's `unplaced`) go to a chat model first (yes_ask.py), the turn
  judged meanwhile (`landed`): its `yes` or `send`, within the rails, is held as the lists' yes
  is; its `no` or `change`, unless the words are the agent's own lines heard back, declines the
  read-back so, stopping it if it still plays, and the turn reaches the talker; any other word
  counts for nothing. Any other words drop a yes held before them.
- **In the order said.** Words count in the order their speech began, never the order their
  transcripts came: no yes is held once words begun after it over the same read-back dropped
  one, or would have (`_keep`); and words over the summary begun before words a chat model is
  still judging decide nothing (`stale`), so they never cancel that request.
- **Booked** (`book`, after each step of the session's: yes_turns.py's `flush`). Once the
  summary has played whole, and `turns.vad_start_ms` and `LAG_S` more have passed since (the
  speech detector reports a turn only once its speech has lasted that long, its start
  backdated, so a turn begun before the summary's end opens that late; a step of the
  session's then, `_wake`), with no other words begun since (`_quiet`: no turn open or awaiting
  its words, no overlap of the call undecided, no model's word awaited), the receipt is built as
  for any answer, and the yes rule issues the confirmed action from the held turn's own words
  (domain/yes_rule.py's `held`): the closing question, if it still plays, is cut, and the
  action's `sending` line is said as the reply answering the held turn, the action then sent as
  a yes after the question is (yes_turns.py). A yes the rule refuses then is dropped, and the
  read-back goes on as with none.
- **Dropped.** A held yes is of one read-back only (`current`): a new read-back, a decline, a
  repeat, the client's stop or the call's end leaves it void. An answer the yes rule takes once
  the summary played drops it and decides as any answer does, but one of only fillers and
  listening sounds counts for nothing, and the held yes books (`answered`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_kinds import ModelWord, SaidLines, echoes, held_yes, playing
from t2_agentic_voice.domain.yes_rule import AskAgain, Yes, YesOutcome, held
from t2_agentic_voice.domain.yes_words import covered
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.overlap import call_words
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.read_back_heard import unplaced
from t2_agentic_voice.voice.session.read_back_times import ReadBack
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.yes_ask import Receipt, YesAsks, said_lines

_log = get_logger(__name__)
# What decided a held yes: the yes rule's lists, or a chat model's word within its rails.
HeldBy = Literal["words", "model"]
# What carries out the yes the rule issued for a held yes (yes_turns.py's): the turn, its words,
# the receipt, the yes, the plan, the time, and what decided it.
Book = Callable[
    [TurnLog, HeardWords, ReadBackReceipt, YesOutcome, ReadBackPlan, float, HeldBy],
    Awaitable[None],
]
# What answers a turn whose words declined the read-back (talking.py's `answer`).
Talk = Callable[[TurnLog, HeardWords, float], Awaitable[None]]
# How long past the speech detector's start a held yes waits after the summary's end before it
# books: the pipeline's lag between the detector's frames and the session's step (the module's
# Booked).
LAG_S: Final = 0.2


@dataclass(frozen=True, kw_only=True)
class Held:
    """A yes held on `read_back`: the turn that said it, its own heard words, and the chat
    model's `word` on them (None for the lists' yes)."""

    read_back: ReadBack
    turn: TurnLog
    heard: HeardWords
    word: ModelWord


class HeldYes:
    """One call's yes held over a read-back (the module's docstring), said by `speaker`, over
    the turns `turns` keeps, the call's `confirming` state read and declined, the receipt built
    by `receipt`, unplaced words asked of a model by `asks`; a declined turn answered by
    `talk`, a yes the rule issued carried out by `book`, and a step due later run as `guarded`
    runs it, the session's `sync`."""

    def __init__(
        self,
        setup: CallSetup,
        *,
        speaker: Speaker,
        turns: TurnBook,
        confirming: Confirming,
        receipt: Receipt,
        asks: YesAsks,
        talk: Talk,
        book: Book,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
    ) -> None:
        self._setup, self._speaker, self._turns, self._confirming = (
            setup,
            speaker,
            turns,
            confirming,
        )
        self._receipt, self._asks, self._talk, self._book = receipt, asks, talk, book
        self._guarded, self._sync, self._clock = guarded, sync, setup.clock
        self._wait_s = setup.settings.turns.vad_start_ms / 1000 + LAG_S
        self._held: Held | None = None
        self._after: tuple[ReadBack, float] | None = None  # the latest words that drop a yes
        self._waking: asyncio.Task[None] | None = None

    def current(self) -> Held | None:
        """The yes held on the current read-back; None when none is, or it was of another."""
        kept = self._held
        if kept is not None and kept.read_back is not self._confirming.read_back:
            self._held = kept = None
        return kept

    async def over_summary(
        self, turn: TurnLog, heard: HeardWords, read_back: ReadBack, at: float
    ) -> None:
        """`turn`'s words `heard`, said over `read_back`'s summary, at `at` (the module's
        Held): held, kept beside a yes held, put to a model, or dropping a yes held."""
        words = self._confirming.words(read_back.plan)
        if held_yes(None, heard.text, words, said=self._said(read_back, heard)):
            self._keep(Held(read_back=read_back, turn=turn, heard=heard, word=None))
            return
        call = call_words(self._setup)
        if covered(heard.text, (*words.fillers, *call.backchannel)):
            return
        self._drop("words", heard)
        if self._confirming.asks and unplaced(heard.text, words, words=call):
            self._asks.start(turn, heard, None, read_back)

    async def landed(
        self, turn: TurnLog, heard: HeardWords, word: ModelWord, read_back: ReadBack, at: float
    ) -> None:
        """A chat model's `word` on `turn`'s words over `read_back`'s summary (yes_ask.py), at
        `at`, `read_back` still current: held, the read-back declined, or nothing."""
        plan, said = read_back.plan, self._said(read_back, heard)
        words = self._confirming.words(plan)
        rails = self._asks.rails(heard, words, plan)
        if word in ("yes", "send") and held_yes(word, heard.text, words, said=said, rails=rails):
            self._keep(Held(read_back=read_back, turn=turn, heard=heard, word=word))
            return
        if word not in ("no", "change") or echoes(rule_form(heard.text), playing(said, over=True)):
            return  # counts for nothing; the agent's echo never declines a read-back
        reply = self._speaker.playback.reply(read_back.reply_id)
        self._confirming.decline(turn.turn_id, "no" if word == "no" else "correction")
        if reply is not None and reply.ended_at is None:  # the read-back plays: it is stopped
            turn.cut_reply = read_back.reply_id
            await self._speaker.stop(at, client=False)
        await self._talk(turn, heard, at)

    def answered(self, heard: HeardWords) -> bool:
        """Whether `heard`, a turn's words that answer the read-back once its summary played,
        count for nothing beside a yes held on it: only fillers and listening sounds, the held
        yes then booked at once (`book`); any other words drop it (the module's Dropped), and
        no yes begun before them is held after."""
        read_back = self._confirming.read_back
        if read_back is None:
            return False
        words = self._confirming.words(read_back.plan)
        if covered(heard.text, (*words.fillers, *call_words(self._setup).backchannel)):
            return self.current() is not None
        self._drop("answered", heard)
        return False

    def stale(self, heard: HeardWords) -> bool:
        """Whether `heard`, a turn's words over the current read-back's summary, began before
        words a chat model is still judging: they decide nothing (the module's docstring)."""
        return not self._confirming.answering(heard.speech_at) and self._asks.after(heard)

    async def book(self, at: float) -> None:
        """The yes held on the current read-back, booked at `at` once it is due (the module's
        Booked); nothing before then, or with none held."""
        kept = self.current()
        if kept is None or not self._quiet():
            return
        receipt = self._receipt(at, quiet=True)
        if receipt is None:
            return
        due = receipt.summary_played_at + self._wait_s
        if at < due:  # a turn begun before the summary's end may open yet (the module's Booked)
            self._wake(due - at)
            return
        self._held = None
        read_back, heard, plan = kept.read_back, kept.heard, kept.read_back.plan
        outcome = self._issued(kept, receipt)
        if not isinstance(outcome, Yes):
            self._line("read_back_yes_dropped", kept.turn, why="refused")
            return
        reply = self._speaker.playback.reply(read_back.reply_id)
        if reply is not None and reply.ended_at is None:  # its closing question: cut, or unsaid
            await self._speaker.stop(at, client=False)
        by: HeldBy = "words" if kept.word is None else "model"
        await self._book(kept.turn, heard, receipt, outcome, plan, at, by)
        self._turns.ended(kept.turn, "answered")

    def end(self) -> None:
        """The call ended: nothing held books."""
        self._held = None
        if self._waking is not None:
            self._waking.cancel()
            self._waking = None

    def _wake(self, wait: float) -> None:
        """A step of the session's in `wait` seconds (`sync`, which books a yes held then due),
        one at a time."""
        if self._waking is None:
            self._waking = asyncio.create_task(self._woken(wait), name="held-yes-due")

    async def _woken(self, wait: float) -> None:
        await self._clock.sleep(wait)
        self._waking = None
        await self._guarded("held_yes_due", self._sync)

    def _issued(self, kept: Held, receipt: ReadBackReceipt) -> Yes | AskAgain:
        """The yes rule's word on `kept` with `receipt` (`held`): never a yes when it fails."""
        plan, heard = kept.read_back.plan, kept.heard
        try:
            words = self._confirming.words(plan)
            return held(
                kept.word,
                heard,
                receipt,
                words=words,
                env=self._setup.settings.env,
                said=self._said(kept.read_back, heard),
                rails=self._asks.rails(heard, words, plan),
            )
        except Exception as error:  # a bug: never a yes
            self._line("yes_rule_failed", kept.turn, failure=type(error).__qualname__)
            return AskAgain()

    def _quiet(self) -> bool:
        """Whether no other words are on the way: no turn open or awaiting its transcript, and
        no chat model's word awaited (the receipt's `quiet` reads the overlaps)."""
        return self._turns.all_heard and not self._asks.busy

    def _keep(self, kept: Held) -> None:
        """`kept` is held, unless a yes is held on the read-back already (it stays), or words
        begun after it dropped one (the module's In the order said)."""
        later, began = self._later(), kept.heard.speech_at
        if later is not None and (began is None or began < later):
            self._line("read_back_yes_dropped", kept.turn, why="later_words")
            return
        if self.current() is None:
            self._held = kept
            self._line(
                "read_back_yes_held", kept.turn, by="words" if kept.word is None else "model"
            )

    def _drop(self, why: str, heard: HeardWords) -> None:
        """`heard`, words other than a yes, were said over the current read-back: a yes held is
        dropped, and they are the latest words that drop one when they began last (`_later`)."""
        read_back, began, last = self._confirming.read_back, heard.speech_at, self._later()
        if read_back is not None and began is not None:
            self._after = (read_back, began if last is None else max(last, began))
        kept = self.current()
        if kept is not None:
            self._held = None
            self._line("read_back_yes_dropped", kept.turn, why=why)

    def _later(self) -> float | None:
        """When the latest words over the current read-back that drop a yes began; None for
        none."""
        after = self._after
        if after is None or after[0] is not self._confirming.read_back:
            return None
        return after[1]

    def _said(self, read_back: ReadBack, heard: HeardWords) -> SaidLines:
        """The read-back's lines as the echo rail reads them for words said over its summary."""
        began = heard.speech_at
        asked = self._confirming.over_follow_up(began)
        return said_lines(read_back.plan, over_read_back=True, over_asked_again=asked)

    def _line(self, line: str, turn: TurnLog, **fields: str) -> None:
        _log.info(line, call_id=self._setup.call_id, turn_id=turn.turn_id, **fields)
