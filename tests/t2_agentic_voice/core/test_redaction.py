"""The Redactor. Plan 002's Track C builds it and replaces this file's stub test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.redaction import Redactor


def test_the_redactor_is_a_stub_until_track_c() -> None:
    with pytest.raises(NotImplementedError, match="Track C"):
        Redactor([r"\d{10}"])
    stub = Redactor.__new__(Redactor)  # the method's stub, past the constructor's
    with pytest.raises(NotImplementedError, match="Track C"):
        stub("0512345678")
