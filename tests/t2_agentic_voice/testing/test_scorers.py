"""wer and cer. Plan 002's Track A builds them on jiwer and replaces this file's stub tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from t2_agentic_voice.testing.scorers import cer, wer


@pytest.mark.parametrize("scorer", [wer, cer])
def test_the_error_rates_are_stubs_until_track_a(
    scorer: Callable[[Sequence[str], Sequence[str]], float],
) -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        scorer(["a b"], ["a c"])
