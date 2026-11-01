"""A run's scorecard: its totals and breakdowns, labelled one speaker.

Built by plan 002's Track F; until then a stub.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ole5_voice.evals.models import RunInfo, Scorecard, VariantResult

_STUB = "scorecard.py is built by plan 002's Track F"


def write_scorecard(
    run: RunInfo, results: Sequence[VariantResult], *, complete: bool, out: Path
) -> Scorecard:
    """The scorecard of `results` (a `ScorecardWriter`), also written below `out`."""
    raise NotImplementedError(_STUB)
