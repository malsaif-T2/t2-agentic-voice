"""Fixtures of the adapters' tests."""

from __future__ import annotations

import pytest
from t2_agentic_voice.adapters import clause_cache

from tests.t2_agentic_voice.adapters.clause_support import RELAXED_READ_S


@pytest.fixture
def relaxed_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clause cache's read limit raised to `RELAXED_READ_S`, for each test that is not about
    the limit; the test of a slow read sets the limit it is about itself."""
    monkeypatch.setattr(clause_cache, "READ_TIMEOUT_S", RELAXED_READ_S)
