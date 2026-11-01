"""A recall count: found among expected, never more."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice.domain.recall import Recall


def test_a_recall_is_two_counts() -> None:
    assert Recall(expected=3, found=2).model_dump() == {"expected": 3, "found": 2}
    assert Recall(expected=0, found=0).found == 0


@pytest.mark.parametrize(
    "counts", [{"expected": 1, "found": 2}, {"expected": -1, "found": 0}, {"expected": 1}]
)
def test_an_impossible_count_is_refused(counts: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Recall.model_validate(counts)
