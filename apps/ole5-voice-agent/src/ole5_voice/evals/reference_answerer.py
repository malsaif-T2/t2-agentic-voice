"""The `reference` answerer of `poe eval`, which gives each variant its own reference and sends
nothing: the harness checking itself (evaluation.md, "Proven twice"), in a module of its
own as each answerer is.
"""

from __future__ import annotations

from ole5_voice.evals.models import Variant
from ole5_voice.evals.runs import Answer, AnswerRequest
from ole5_voice.evals.windows import Measure


def measured(measure: Measure | None) -> Measure:
    """`measure`, which an answerer asked for windows needs; ValueError when it has none."""
    if measure is None:
        raise ValueError("an answerer asked for windows needs a Measure")
    return measure


class ReferenceAnswerer:
    """Gives each variant its own reference, as every window's text too, and sends nothing:
    the harness checking itself (evaluation.md, "Proven twice")."""

    name = "reference"
    spends = False
    needs_audio = False

    def __init__(self, measure: Measure | None = None) -> None:
        self._measure = measure

    async def answer(self, variant: Variant, request: AnswerRequest) -> Answer:
        if not request.windows_ms:
            return Answer(variant=variant.id, text=variant.reference)
        measure = measured(self._measure)
        found = [
            measure(variant.reference, ms, variant.reference, False) for ms in request.windows_ms
        ]
        return Answer(variant=variant.id, windows=tuple(found))

    async def aclose(self) -> None:
        """Nothing is held open."""
