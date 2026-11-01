"""sign_test. Plan 002's Track A builds it and replaces this file's stub test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.sign_test import sign_test


def test_sign_test_is_a_stub_until_track_a() -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        sign_test(6, 0)
