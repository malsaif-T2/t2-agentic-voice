"""A chat model's word on an answer to an action's read-back that the yes rule's lists leave
unplaced (D-082; the owner's rulings of 2026-11-10), for yes_turns.py.

**When.** Only for an agent that asks (`VoiceAgent.ask_on_unlisted_answers`), in a call with a
chat model (`CallSetup.overlap_model`, the call's chat model for the session's own requests),
and only for words `decide` marked `askable` (domain/yes_rule.py): every other answer is the
lists' and asks nothing (`wanted`). One request a turn, and one at a time.

**The request** (domain/consent_check.py's) holds the read-back's summary and closing question
as its plan rendered them and the turn's own heard words, nothing else. It is the session's own
timed chat request (model_word.py), within `TIMEOUT_S`, and runs as a task of a cancel scope of
its own, holding no lock of the session's: only its answer lands as a step of the session's
(`guarded`, under its lock), so no other step waits on the model. A failure or a timeout is no
word. Each outcome is logged by its kind alone, never the words.

**The verdict** is the yes rule's (`judged`), never the model's word as it is, carried out by
yes_turns.py as any answer is, told `by="model"`; and only while the same read-back is current
and the call has not ended and is not ending. No word, on words that hold a no word of the
lists, is declined, as the model's `no` is (the owner's "Yes, all three", 2026-11-11); on any
other words, or on the agent's own lines heard back, it is asked again. The rule is handed
the read-back's lines (`said_lines`) and whether the read-back, and a line that asked it
again, were still heard as the turn's speech began, each reply playing or within its tail
after it ended (read_back.py's `over_read_back` and `over_follow_up`), so its echo rail reads
only a line the caller was hearing; and, for words heard in another language than the
read-back's, the no words and change markers of every language the agent speaks
(domain/yes_words.py's `rails_for`), so an English "yes, but ..." over an
Arabic read-back is a correction.
A newer turn that answers the read-back cancels a request still in flight (`cancel`, which
yes_turns.py calls first), and so do the client's stop (`cancel`) and the call's end: each
decides nothing.

**Over the summary** (D-108, under `interruptions.yes_over_read_back`): held_yes.py asks about
words the lists leave unplaced over the read-back's summary, with no receipt yet (`start` with
none); the model's word, while the same read-back is current, goes to it as it is (`hold`), and
the yes rule reads it, within its rails, once the summary has played whole.

**The turn** is judged meanwhile (turn_book.py's `judging`): it takes no fate and does not
settle, so its times run to the first audio of the reply its verdict says, the wait included,
and its trace stays open for that reply. Once the verdict is carried out, or the request
dropped, it is `judged`: answered by nothing when no reply answers it (unless the call has ended
or is ending, when the call's end leaves it unfinished), and settled as any turn is.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Final, Literal, Protocol

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords, ReadBackReceipt
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.consent_check import (
    TIMEOUT_S,
    ConsentAnswer,
    consent_check_answer,
    consent_check_request,
)
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.domain.yes_kinds import ModelWord, SaidLines
from t2_agentic_voice.domain.yes_rule import AskAgain, Correction, YesOutcome, judged
from t2_agentic_voice.domain.yes_words import ConsentWords, rails_for
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.model_word import model_word
from t2_agentic_voice.voice.session.open_reply import language_of
from t2_agentic_voice.voice.session.read_back import Confirming, ReadBack
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.turn_book import TurnBook

_log = get_logger(__name__)
# What became of a request: the model's word, or that it failed or timed out.
Outcome = ConsentAnswer | Literal["failed", "timeout"]


class Receipt(Protocol):
    """The current read-back's receipt for speech begun at a time, built now (interrupter.py's);
    with `quiet`, None too while any overlap of the call is undecided (held_yes.py)."""

    def __call__(
        self, speech_at: float | None, /, *, quiet: bool = False
    ) -> ReadBackReceipt | None: ...


# What carries out the yes rule's verdict on a turn, by a model's word (yes_turns.py's): the
# turn, its words, the receipt built when they reached the rule, the verdict, the plan, the time.
Settle = Callable[
    [TurnLog, HeardWords, ReadBackReceipt, YesOutcome, ReadBackPlan, float], Awaitable[None]
]
# What takes a model's word on words over the summary, with no receipt yet (held_yes.py's): the
# turn, its words, the word, the read-back they were said over, the time.
Hold = Callable[[TurnLog, HeardWords, ModelWord, ReadBack, float], Awaitable[None]]
_STEP: Final = "yes_model"


def _word(outcome: Outcome) -> ModelWord:
    """The model's word of `outcome`; None when it gave none (it failed or timed out)."""
    if outcome == "failed" or outcome == "timeout":
        return None
    return outcome


def said_lines(plan: ReadBackPlan, *, over_read_back: bool, over_asked_again: bool) -> SaidLines:
    """What the agent says of `plan`'s read-back, written and spoken, the words its echo would
    be made of: its summary and closing question, and its ask-again line, with whether the
    caller's speech began while each was still heard (`over_read_back`, `over_asked_again`:
    read_back.py's `Confirming.over_read_back` and `over_follow_up`, each reply's tail
    included)."""

    def forms(*lines: SpokenLine) -> tuple[str, ...]:
        return tuple(text for line in lines for text in (line.text, line.spoken))

    return SaidLines(
        read_back=forms(plan.summary, plan.question),
        asked_again=forms(plan.asked_again),
        over_read_back=over_read_back,
        over_asked_again=over_asked_again,
    )


def said_of(confirming: Confirming, plan: ReadBackPlan, began: float | None) -> SaidLines:
    """`said_lines` of `plan`, with whether speech begun at `began` began while the read-back,
    and a line that asked it again, were still heard (`confirming`'s)."""
    over, asked = confirming.over_read_back(began), confirming.over_follow_up(began)
    return said_lines(plan, over_read_back=over, over_asked_again=asked)


@dataclass(frozen=True, kw_only=True)
class _Ask:
    """One request in flight: the turn it answers, its words, the receipt built when they
    reached the rule (none for words over the summary), the read-back they answer, and the
    scope its work runs in."""

    turn: TurnLog
    heard: HeardWords
    receipt: ReadBackReceipt | None
    read_back: ReadBack
    scope: CancelScope


class YesAsks:
    """One call's requests for a chat model's word on an answer (the module's docstring): each
    started (`start`) in a scope of its own, its turn judged in `turns` meanwhile, its verdict
    landed as a step `guarded` runs and carried out by `settle` (by `hold`, for words over the
    summary), the client then told by `sync`; `over` says whether the call has ended or is
    ending, `receipt` builds the current read-back's receipt."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        turns: TurnBook,
        confirming: Confirming,
        receipt: Receipt,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        over: Callable[[], bool],
        settle: Settle,
        hold: Hold,
    ) -> None:
        self._setup, self._usage, self._clock, self._turns = setup, books.usage, setup.clock, turns
        self._confirming, self._receipt, self._settle, self._hold = (
            confirming,
            receipt,
            settle,
            hold,
        )
        self._guarded, self._sync, self._over = guarded, sync, over
        self._asks = setup.agent.ask_on_unlisted_answers and setup.overlap_model is not None
        self._ask: _Ask | None = None

    def wanted(self, outcome: YesOutcome) -> bool:
        """Whether the lists' `outcome` is put to the model: the agent asks, and the lists left
        the words unplaced."""
        return self._asks and isinstance(outcome, Correction | AskAgain) and outcome.askable

    @property
    def busy(self) -> bool:
        """Whether a request is in flight."""
        return self._ask is not None

    def start(
        self,
        turn: TurnLog,
        heard: HeardWords,
        receipt: ReadBackReceipt | None,
        read_back: ReadBack,
    ) -> None:
        """Ask the model about `turn`'s words `heard`, answering `read_back`, `receipt` the one
        built as they reached the rule (None for words over its summary: `hold` takes the word);
        the turn judged until its word lands or is dropped."""
        plan = read_back.plan
        request = consent_check_request(plan.summary.text, plan.question.text, heard.text)
        scope = CancelScope(name=f"yes-check-{turn.turn_id}", clock=self._clock)
        ask = _Ask(turn=turn, heard=heard, receipt=receipt, read_back=read_back, scope=scope)
        self._ask = ask
        self._turns.judging(turn)
        scope.start(self._run(ask, request), name=f"yes-check-ask-{turn.turn_id}")

    async def cancel(self) -> None:
        """A newer turn answers the read-back, the client stopped, or the call ended: the
        request still in flight is cancelled, and decides nothing; its turn is judged."""
        ask, self._ask = self._ask, None
        if ask is None:
            return
        await ask.scope.cancel()
        _log.info(
            "yes_model_dropped", call_id=self._setup.call_id, turn_id=ask.turn.turn_id, why="cancel"
        )
        self._turns.judged(ask.turn, answered=not self._over())

    async def _run(self, ask: _Ask, request: ChatRequest) -> None:
        """The request, within its timeout on the call's clock, then its answer, read as one
        word, landed as a step of the session's; a cancel stops both."""
        outcome: Outcome = await model_word(
            self._setup,
            self._usage,
            request,
            consent_check_answer,
            scope=ask.scope,
            timeout_s=TIMEOUT_S,
            name="yes-check",
            turn_id=ask.turn.turn_id,
            failed_line="yes_model_failed",
        )
        await self._guarded(_STEP, partial(self._landed, ask, outcome))

    def rails(self, heard: HeardWords, words: ConsentWords, plan: ReadBackPlan) -> ConsentWords:
        """The lists `judged`'s rails read for `heard` (the module's docstring)."""
        code = language_of(self._setup, plan.language).primary
        spoken = [each.primary for each in self._setup.agent.languages]
        return rails_for(words, heard=heard.language, read_back=code, spoken=spoken)

    async def _landed(self, ask: _Ask, outcome: Outcome) -> None:
        """The request's answer, as a step of the session's: the yes rule's verdict on it,
        carried out, while the same read-back is current and the call goes on; nothing when a
        cancel took it first. Its turn is judged then, whatever came of it."""
        if self._ask is not ask:
            return
        self._ask = None
        try:
            await self._verdict(ask, outcome)
        finally:
            self._turns.judged(ask.turn, answered=not self._over())

    async def _verdict(self, ask: _Ask, outcome: Outcome) -> None:
        """The yes rule's verdict on `outcome`, carried out and the client told, unless the
        call has ended or is ending or `ask`'s read-back is no longer current."""
        call_id, turn_id = self._setup.call_id, ask.turn.turn_id
        if self._over() or self._confirming.read_back is not ask.read_back:
            _log.info("yes_model_dropped", call_id=call_id, turn_id=turn_id, why="stale")
            return
        plan, began, confirming = ask.read_back.plan, ask.heard.speech_at, self._confirming
        if ask.receipt is None:  # words over the summary: the word as it is (held_yes.py)
            _log.info("yes_model_answered", call_id=call_id, turn_id=turn_id, answer=outcome)
            await self._hold(ask.turn, ask.heard, _word(outcome), ask.read_back, self._clock.now())
            await self._sync()
            return
        try:
            said, words = said_of(confirming, plan, began), confirming.words(plan)
            verdict = judged(
                _word(outcome),
                ask.heard,
                ask.receipt,
                current=self._receipt(began),
                words=words,
                env=self._setup.settings.env,
                said=said,
                rails=self.rails(ask.heard, words, plan),
                bare=confirming.holds_yes,
            )
        except Exception as error:  # a bug: never a yes
            failure = type(error).__qualname__
            _log.error("yes_rule_failed", call_id=call_id, turn_id=turn_id, failure=failure)
            verdict = AskAgain()
        _log.info("yes_model_answered", call_id=call_id, turn_id=turn_id, answer=outcome)
        await self._settle(ask.turn, ask.heard, ask.receipt, verdict, plan, self._clock.now())
        await self._sync()
