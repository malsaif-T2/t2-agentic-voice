"""Smart Turn v3.2 with the settings' threshold (`turns.smart_turn_threshold`): Pipecat 1.15.0's
`LocalSmartTurnAnalyzerV3` fixes it at 0.5 (`local_smart_turn_v3.py`, line 174, `prediction = 1
if probability > 0.5`), and its base reads only that `prediction` to end a turn
(`base_smart_turn.py`, lines 243-258), though it hands on the probability too.

`ThresholdSmartTurn` overrides `_predict_endpoint` (line 138), a private method of 1.15.0: it
calls Pipecat's own and recomputes the prediction from its probability, so at 0.5 a turn ends as
it did. With `keep_turn` (on when `turns.complete_hold_ms` is above 0, turn_hold.py) it also
keeps the turn's audio when it judges a pause complete, so a turn that goes on through the hold
is judged whole at its next pause: it overrides the private `_clear` (`base_smart_turn.py`, line
199), skipping it only while `analyze_end_of_turn` runs (its call, line 166); the silence
fallback's clear (line 138) and the turn's end (`clear`, line 174, which the stop strategy calls
when the turn ends) still drop it.

Each judgement the model makes is logged as it ends (`smart_turn_judged`, numbers alone): its
verdict and probability, the model's own time as Pipecat measures it (`TurnMetricsData`'s
`e2e_processing_time_ms`, `model_ms`: resampling, features and the ONNX run), and where the rest
of the judgement's time went: the wait for the model's one thread (`wait_ms`), the turn's audio
joined in it (`join_ms`), and the event loop taking the verdict back (`back_ms`), with the
audio judged (`audio_s`); it overrides the private `_process_speech_segment` (line 207), which
the model's thread runs, only to time it. An upgrade of Pipecat must check that these methods,
their calls and the result's two keys are still there (the tests compare it with Pipecat's own). Its
module imports onnxruntime, so voice/turns.py imports it only when it builds one, as it imports
Pipecat's.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.metrics.metrics import MetricsData, TurnMetricsData

from t2_agentic_voice.core.logging import get_logger

_log = get_logger(__name__)


class ThresholdSmartTurn(LocalSmartTurnAnalyzerV3):
    """Pipecat's local Smart Turn v3.2, a pause ending the turn when the model's probability that
    the caller has finished is above `threshold` (0 to 1), the turn's audio kept through that
    verdict when `keep_turn`; the other arguments are Pipecat's."""

    def __init__(self, *, threshold: float, keep_turn: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.threshold = threshold
        self.keep_turn = keep_turn
        self._judging = False
        self._began = self._ended = self._audio_s = 0.0  # the model thread's last judgement

    def _predict_endpoint(self, audio_array: Any) -> dict[str, Any]:
        """Pipecat's prediction for `audio_array` (its numpy array, a dependency the library
        does not declare), made again from its probability with the threshold."""
        result = super()._predict_endpoint(audio_array)
        return {**result, "prediction": 1 if result["probability"] > self.threshold else 0}

    async def analyze_end_of_turn(self) -> tuple[EndOfTurnState, MetricsData | None]:
        """Pipecat's judgement of the pause, the turn's audio kept after it when `keep_turn`,
        logged with its times when the model ran (the module's docstring)."""
        self._judging = True
        asked = perf_counter()
        try:
            state, metrics = await super().analyze_end_of_turn()
        finally:
            self._judging = False
        if isinstance(metrics, TurnMetricsData):
            self._log(metrics, asked, perf_counter())
        return state, metrics

    def _process_speech_segment(
        self, audio_buffer: Any
    ) -> tuple[EndOfTurnState, MetricsData | None]:
        """Pipecat's judgement of `audio_buffer` (its timed chunks), in the model's thread,
        timed (the module's docstring)."""
        self._began = perf_counter()
        try:
            self._audio_s = sum(len(chunk) for _, chunk in audio_buffer) / (self.sample_rate or 1)
            return super()._process_speech_segment(audio_buffer)
        finally:
            self._ended = perf_counter()

    def _log(self, metrics: TurnMetricsData, asked: float, back: float) -> None:
        model_ms = metrics.e2e_processing_time_ms
        _log.info(
            "smart_turn_judged",
            complete=metrics.is_complete,
            probability=round(metrics.probability, 3),
            model_ms=round(model_ms, 1),
            wait_ms=round((self._began - asked) * 1000, 1),
            join_ms=round((self._ended - self._began) * 1000 - model_ms, 1),
            back_ms=round((back - self._ended) * 1000, 1),
            total_ms=round((back - asked) * 1000, 1),
            audio_s=round(self._audio_s, 2),
        )

    def _clear(self, turn_state: EndOfTurnState) -> None:
        """Pipecat's clear, but for the one after a verdict while `keep_turn`."""
        if not (self._judging and self.keep_turn):
            super()._clear(turn_state)
