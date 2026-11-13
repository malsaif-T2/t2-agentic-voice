"""The chat model's word on an uncertain overlap (D-069; plan 006, Q28), for interrupter.py: when
the rule lets a short overlap of two or more words go on (overlap.py's `Overlaps.judge`, with
domain/uncertain_overlaps.py's `is_uncertain`), one request asks a chat model, and the overlap
stays undecided, the agent's voice ducked and the reply playing on, until it answers.

**The request** is the session's own timed chat request (model_word.py), within `TIMEOUT_S`. It
runs as a task of a cancel scope of the overlap's own (scope.py), never the reply's, which ends
with the reply, and it holds no lock of the session's: only its verdict is applied as a step of
the session's (`guarded`, under its lock), so no other step waits on the model (`handle` stays
prompt, the `Session` protocol's rule). Any answer but `stop`, a failure or a timeout leaves the
rule's verdict, the outcome logged by its kind alone, never the words.

**The verdict.** `stop` is `MODEL_STOP`, new words, as the rule's step 7 gives, and the turn's
own transcript goes to the talker as for any new request (interrupter.py's `model_said`, once the
call has not ended and is not ending); else the rule's go-on. The overlap ends with exactly one
`unduck`, whatever decides it.

**A stop or the call's end during the wait.** A stop that drops the replies (`stopped`: the
speaker's word, whoever asked) cancels the request and the rule's verdict stands, its one `unduck`
then sent; the call's end (`end`) cancels it and decides nothing, as for any overlap the end cuts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Final, Literal

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.domain.uncertain_overlaps import (
    MODEL_STOP,
    TIMEOUT_S,
    UncertainAnswer,
    uncertain_overlap_answer,
    uncertain_overlap_request,
)
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.model_word import model_word
from t2_agentic_voice.voice.session.overlap import OverlapState
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.session_events import Transcribed

_log = get_logger(__name__)
# What became of a request: the model's word, or that it failed, timed out, or that a stop cut it.
Outcome = UncertainAnswer | Literal["failed", "timeout", "stopped"]
# What carries out the verdict on the overlap: the session's step (interrupter.py's `model_said`).
Decide = Callable[[OverlapState, Verdict, Transcribed, float], Awaitable[None]]
_STEP: Final = "overlap_model"


@dataclass(frozen=True, kw_only=True)
class _Ask:
    """One request in flight: the overlap it decides, the rule's verdict and transcript it was
    asked about, and the scope its work runs in, that a stop or the call's end cancels."""

    state: OverlapState
    verdict: Verdict
    event: Transcribed
    scope: CancelScope


class OverlapAsks:
    """One call's requests to the chat model (the module's docstring): each one started
    (`start`) in a scope of its own, its verdict applied as a step `guarded` runs (`decide`),
    `over` saying whether the call has ended or is ending."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        guarded: Guarded,
        over: Callable[[], bool],
        decide: Decide,
    ) -> None:
        self._setup, self._usage = setup, books.usage
        self._guarded, self._over, self._decide = guarded, over, decide
        self._clock = setup.clock
        self._asks: dict[TurnId, _Ask] = {}

    def start(self, state: OverlapState, reply: str) -> None:
        """Ask the model about `state`'s transcript (`state.asking`), said over `reply`."""
        model, asking = self._setup.overlap_model, state.asking
        if model is None or asking is None:  # never so: the overlap asked only with a model
            return
        transcript = asking.event.transcript
        words = "" if transcript is None else transcript.text
        request = uncertain_overlap_request(reply, words)
        scope = CancelScope(name=f"overlap-{state.turn_id}", clock=self._clock)
        ask = _Ask(state=state, verdict=asking.verdict, event=asking.event, scope=scope)
        self._asks[state.turn_id] = ask
        scope.start(self._run(ask, request), name=f"overlap-ask-{state.turn_id}")

    async def stopped(self, at: float) -> None:
        """The session dropped the replies (`Speaker.stop`, whoever asked): every request still
        in flight cancelled, its overlap decided by the rule's verdict, its `unduck` then sent."""
        for turn_id in list(self._asks):
            ask = self._asks.pop(turn_id)
            await ask.scope.cancel()
            await self._decided(ask, "stopped", at)

    async def end(self) -> None:
        """The call ended: every request in flight cancelled, its overlap left undecided, as
        any overlap the end cuts (no `unduck`: the client restores the volume at the end)."""
        for ask in list(self._asks.values()):
            await ask.scope.cancel()
        self._asks.clear()

    async def _run(self, ask: _Ask, request: ChatRequest) -> None:
        """The request, within its timeout on the call's clock, then its verdict applied as a
        step of the session's; a stop or the call's end cancels both."""
        outcome: Outcome = await model_word(
            self._setup,
            self._usage,
            request,
            uncertain_overlap_answer,
            scope=ask.scope,
            timeout_s=TIMEOUT_S,
            name="overlap",
            turn_id=ask.state.turn_id,
            failed_line="overlap_model_failed",
        )
        await self._guarded(_STEP, partial(self._landed, ask, outcome))

    async def _landed(self, ask: _Ask, outcome: Outcome) -> None:
        """The request's answer, as a step of the session's; nothing when a stop or the call's
        end took it first (it is then no longer in flight)."""
        if self._asks.get(ask.state.turn_id) is ask:
            del self._asks[ask.state.turn_id]
            await self._decided(ask, outcome, self._clock.now())

    async def _decided(self, ask: _Ask, outcome: Outcome, at: float) -> None:
        """The overlap decided: the model's stop as new words, unless the call has ended or is
        ending; any other outcome the rule's verdict, logged by its kind alone."""
        stops = outcome == "stop" and not self._over()
        verdict = MODEL_STOP if stops else ask.verdict
        _log.info(
            "overlap_model_answered",
            call_id=self._setup.call_id,
            turn_id=ask.state.turn_id,
            answer=outcome,
            verdict=verdict.reason,
        )
        ask.state.settled(verdict)
        await self._decide(ask.state, verdict, ask.event, at)
