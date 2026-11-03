"""Smart Turn v3.2 with the settings' threshold (`turns.smart_turn_threshold`): Pipecat 1.15.0's
`LocalSmartTurnAnalyzerV3` fixes it at 0.5 (`local_smart_turn_v3.py`, line 174, `prediction = 1
if probability > 0.5`), and its base reads only that `prediction` to end a turn
(`base_smart_turn.py`, lines 243-258), though it hands on the probability too.

`ThresholdSmartTurn` overrides `_predict_endpoint` (line 138), a private method of 1.15.0: it
calls Pipecat's own and recomputes the prediction from its probability, so at 0.5 a turn ends as
it did. An upgrade of Pipecat must check that the method and its result's two keys are still
there (the tests compare it with Pipecat's own). Its module imports onnxruntime, so voice/turns.py
imports it only when it builds one, as it imports Pipecat's.
"""

from __future__ import annotations

from typing import Any

from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3


class ThresholdSmartTurn(LocalSmartTurnAnalyzerV3):
    """Pipecat's local Smart Turn v3.2, a pause ending the turn when the model's probability that
    the caller has finished is above `threshold` (0 to 1); the other arguments are Pipecat's."""

    def __init__(self, *, threshold: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.threshold = threshold

    def _predict_endpoint(self, audio_array: Any) -> dict[str, Any]:
        """Pipecat's prediction for `audio_array` (its numpy array, a dependency the library
        does not declare), made again from its probability with the threshold."""
        result = super()._predict_endpoint(audio_array)
        return {**result, "prediction": 1 if result["probability"] > self.threshold else 0}
