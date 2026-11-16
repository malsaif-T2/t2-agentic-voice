"""The caller's answer to an action's read-back (plan 007; the design's 6.4 and 8.3;
docs/SECURITY.md, invariant 1), for voice/session/talking.py, which hands it each turn it would
answer while the call is confirming (read_back.py).

A turn with words heard, whose speech began once the read-back's summary had played its last
clause, is the yes rule's (`takes`), not the talker's: its own heard words (heard.py's, from the
turn's transcript: never a held or an overlap one, nor anything the talker or a tool wrote) go
to domain/yes_rule.py's `decide` with the read-back's receipt, built at that moment
(read_back.py's `Confirming.receipt`), so a verdict that lands late still denies it. What the
rule decides, each the public `ConfirmationAnswered`:

- **yes:** confirming ends; the plan's `sending` line is said as the reply answering the turn,
  then the `ConfirmedAction` goes to the call's `ActionJobs` as a job outside the turn
  (action_job.py), its outcome said at the next turn boundary; nothing said claims the action
  done before then. With no `ActionJobs` (an agent wired with none) the yes is told as the
  `error` notice, and nothing is sent.
- **no** or **correction:** confirming ends, and the turn goes to the talker with the action
  declined as that kind (core/conversation.py's `DeclinedAction`), which answers in its own words
  (the owner's ruling); a correction's new draft is read back anew. For an agent that asks, a
  question or a request for something else is the model's `no` (the owner's answer of
  2026-11-11), so the talker answers it; a model that says `unclear` instead asks it again.
  A check that gives no word (it failed or ran out of time) on words that hold a no word is a
  no too, so a cancel for another action reaches the talker, never the ask-again line (the
  owner's "Yes, all three", 2026-11-11); on any other words it asks again.
- **the call moved** into another language since it was read back (read_back_moved.py): no
  verdict; it is read again in the new language, a new receipt required.
- **unclear**, or no receipt (the summary not played whole with audio, or an overlap of it still
  undecided): the plan's `asked_again` line, at most its `max_attempts` times, each a follow-up
  of the read-back; after the last, the plan's `declined` line, and confirming ends.

The rule failing (a bug) is unclear, logged by its kind alone, never a yes; and a `Yes` whose
confirmed action is not the receipt's, for this turn, unchanged since the rule issued it, is not
taken as one.

**Words the lists leave unplaced** (D-082). For an agent that asks, an answer `decide` marks
`askable` is put to a chat model first (yes_ask.py), and nothing is decided or said, nor the
turn settled, until its word lands: the yes rule's verdict on it (`judged`) is then carried out
as above, the event's `by` `model`, and the turn settles after the reply it says. A turn that
answers the read-back first cancels a request still in flight, so only the newest answer
decides; the client's stop and the call's end cancel it too (`stopped`, `end`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from t2_agentic_voice.core.conversation import DeclineKind
from t2_agentic_voice.core.events import ConfirmationAnswered, ConfirmationDecision, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.yes_rule import (
    AskAgain,
    ConfirmedAction,
    Correction,
    Declined,
    Yes,
    YesOutcome,
    decide,
    is_confirmed,
)
from t2_agentic_voice.voice.session.action_job import ActionJob
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.read_back_moved import moved_since, read_moved
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.yes_ask import Receipt as Receipt
from t2_agentic_voice.voice.session.yes_ask import YesAsks

_log = get_logger(__name__)
# The talker's answer to a turn (talking.py's `Talking.answer`).
Talk = Callable[[TurnLog, HeardWords, float], Awaitable[None]]
# What decided a turn's answer: the yes rule's lists, or a chat model's word within its rails.
DecidedBy = Literal["words", "model"]
# What each of the rule's outcomes is, as `ConfirmationAnswered` names it.
_DECISIONS: dict[type, ConfirmationDecision] = {
    Yes: "yes",
    Declined: "declined",
    Correction: "correction",
    AskAgain: "asked_again",
}


def _issued_for(confirmed: ConfirmedAction, receipt: ReadBackReceipt, turn_id: TurnId) -> bool:
    """Whether `confirmed` is the yes rule's, unchanged since, of `receipt`'s draft and read-back,
    for the caller's turn `turn_id`."""
    found = (confirmed.action, confirmed.draft_json, confirmed.reply_id, confirmed.turn_id)
    wanted = (receipt.action, receipt.draft_json, receipt.reply_id, turn_id)
    return is_confirmed(confirmed) and found == wanted


class YesTurns:
    """One call's answers to its read-backs (the module's docstring), said by `speaker`, the
    call's `confirming` state read and ended, the receipt built by `receipt`, a declined turn
    answered by `talk`; its confirmed actions' writes are `jobs` (action_job.py's, given the
    turns, `guarded`, `sync` and `over`), and its requests for a chat model's word on words the
    lists leave unplaced `asks` (yes_ask.py's, given the same)."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        speaker: Speaker,
        turns: TurnBook,
        confirming: Confirming,
        receipt: Receipt,
        talk: Talk,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        over: Callable[[], bool],
    ) -> None:
        self._setup, self._speaker, self._confirming = setup, speaker, confirming
        self._receipt, self._talk = receipt, talk
        self.jobs = ActionJob(
            setup,
            books,
            speaker=speaker,
            turns=turns,
            confirming=confirming,
            guarded=guarded,
            sync=sync,
            over=over,
        )
        self.asks = YesAsks(
            setup,
            books,
            turns=turns,
            confirming=confirming,
            receipt=receipt,
            guarded=guarded,
            sync=sync,
            over=over,
            settle=self._judged,
        )

    def takes(self, heard: HeardWords | None) -> bool:
        """Whether `heard`, a turn's own words, answer the current read-back: the yes rule's."""
        return heard is not None and self._confirming.answering(heard.speech_at)

    async def answer(self, turn: TurnLog, heard: HeardWords, at: float) -> None:
        """Take `turn`, its words `heard`, as the answer to the current read-back, at `at`: the
        yes rule's word on it, then what follows, or first a chat model's word on words its
        lists leave unplaced, for an agent that asks (the module's docstring)."""
        read_back = self._confirming.read_back
        if read_back is None:  # never so: `takes` said it answers one
            return
        await self.asks.cancel()  # a newer answer: an earlier one's request decides nothing
        plan = read_back.plan
        if moved_since(self._setup, self._speaker.playback, read_back):  # read_back_moved.py
            if not await read_moved(self._setup, self._speaker, self._confirming, turn, plan, at):
                await self._talk(turn, heard, at)
            return
        receipt = self._receipt(heard.speech_at)
        outcome = AskAgain() if receipt is None else self._decided(turn, heard, receipt, plan)
        if receipt is not None and self.asks.wanted(outcome):
            self.asks.start(turn, heard, receipt, read_back)
            return
        await self._settled(turn, heard, outcome, plan, at, by="words")

    async def _judged(
        self,
        turn: TurnLog,
        heard: HeardWords,
        receipt: ReadBackReceipt,
        outcome: YesOutcome,
        plan: ReadBackPlan,
        at: float,
    ) -> None:
        """The yes rule's verdict on a chat model's word (yes_ask.py), carried out as any
        answer's, once checked (`_checked`)."""
        outcome = self._checked(outcome, receipt, turn)
        await self._settled(turn, heard, outcome, plan, at, by="model")

    async def _settled(
        self,
        turn: TurnLog,
        heard: HeardWords,
        outcome: YesOutcome,
        plan: ReadBackPlan,
        at: float,
        *,
        by: DecidedBy,
    ) -> None:
        """`outcome`, decided `by` the lists or a model's word, told and carried out."""
        decision = _DECISIONS[type(outcome)]
        setup = self._setup
        answered = ConfirmationAnswered(
            call_id=setup.call_id,
            turn_id=turn.turn_id,
            at=setup.clock.wall(),
            action=plan.action,
            decision=decision,
            by=by,
        )
        setup.emit(answered)
        _log.info(
            "read_back_answered",
            call_id=setup.call_id,
            turn_id=turn.turn_id,
            decision=decision,
            by=by,
        )
        if isinstance(outcome, Yes):
            await self._confirmed(turn, plan, outcome.confirmed, at)
        elif isinstance(outcome, Declined | Correction):
            kind: DeclineKind = "no" if isinstance(outcome, Declined) else "correction"
            self._confirming.decline(turn.turn_id, kind)
            await self._talk(turn, heard, at)
        else:
            await self._ask_again(turn, plan, at)

    async def flush(self, at: float) -> None:
        """Say each action's outcome now due, at a turn boundary (action_job.py's `flush`)."""
        await self.jobs.flush(at)

    async def stopped(self) -> None:
        """The client's `stop`: a chat model's request still in flight decides nothing."""
        await self.asks.cancel()

    async def end(self) -> None:
        """The call ended: a chat model's request still in flight decides nothing, and an
        outcome still due is never said."""
        await self.asks.cancel()
        self.jobs.end()

    def _decided(
        self, turn: TurnLog, heard: HeardWords, receipt: ReadBackReceipt, plan: ReadBackPlan
    ) -> YesOutcome:
        """The yes rule's word on `heard`, `receipt` the read-back's of `plan`, checked
        (`_checked`): unclear when the rule fails."""
        try:
            words = self._confirming.words(plan)
            outcome = decide(heard, receipt, words=words, env=self._setup.settings.env)
        except Exception as error:  # a bug: never a yes
            failure = type(error).__qualname__
            call_id = self._setup.call_id
            _log.error("yes_rule_failed", call_id=call_id, turn_id=turn.turn_id, failure=failure)
            return AskAgain()
        return self._checked(outcome, receipt, turn)

    def _checked(self, outcome: YesOutcome, receipt: ReadBackReceipt, turn: TurnLog) -> YesOutcome:
        """`outcome`, the yes rule's, by its lists or a model's word: unclear, logged as the
        rule failing, when it is a `Yes` whose confirmed action is not `receipt`'s for `turn`,
        unchanged since the rule issued it (`_issued_for`)."""
        if isinstance(outcome, Yes) and not _issued_for(outcome.confirmed, receipt, turn.turn_id):
            call_id = self._setup.call_id
            _log.error("yes_rule_failed", call_id=call_id, turn_id=turn.turn_id, failure="receipt")
            return AskAgain()
        return outcome

    async def _confirmed(
        self, turn: TurnLog, plan: ReadBackPlan, confirmed: ConfirmedAction, at: float
    ) -> None:
        """A yes: confirming ends; `plan`'s `sending` line said as the reply answering `turn`,
        then `confirmed` handed to the call's `ActionJobs`; with none, the `error` notice, and
        nothing sent."""
        self._confirming.confirmed()
        if not self.jobs.wired:
            call_id = self._setup.call_id
            _log.warning("action_not_sent", call_id=call_id, action=plan.action, reason="no_jobs")
            await self._speaker.notice("error", at)
            return
        speaker, tag = self._speaker, plan.language
        turn.reply_id = await speaker.say_line(
            plan.sending, language=tag, at=at, turn_id=turn.turn_id
        )
        self.jobs.start(confirmed, turn_id=turn.turn_id, language=tag, wording=plan.wording)

    async def _ask_again(self, turn: TurnLog, plan: ReadBackPlan, at: float) -> None:
        """An unclear answer: `plan`'s `asked_again` line as the reply answering `turn`, a
        follow-up of the read-back; after the last, its `declined` line, confirming ended."""
        again = self._confirming.asks_again()
        line = plan.asked_again if again else plan.declined
        reply_id = await self._speaker.say_line(
            line, language=plan.language, at=at, turn_id=turn.turn_id
        )
        turn.reply_id = reply_id
        if again:
            self._confirming.follow_up(reply_id)
