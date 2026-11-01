"""normalize_arabic. Plan 002's Track A builds it and replaces this file's stub test with its
own tests (the characterization table: tests/t2_agentic_voice/fixtures/)."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.arabic import normalize_arabic


def test_normalize_arabic_is_a_stub_until_track_a() -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        normalize_arabic("x")
