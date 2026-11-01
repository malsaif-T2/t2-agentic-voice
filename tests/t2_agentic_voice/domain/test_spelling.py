"""spelling_issues. Plan 002's Track A builds it and replaces this file's stub test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.spelling import spelling_issues


def test_spelling_issues_is_a_stub_until_track_a() -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        spelling_issues("x", [])
