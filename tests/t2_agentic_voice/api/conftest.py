"""Fixtures of the api tests (plan 003)."""

from __future__ import annotations

import pytest

from tests.t2_agentic_voice.api.runtime_support import patch_stores


@pytest.fixture
def patched_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    """The adapters' phrase cache and used-token store swapped for fakes, which the runtime's
    lifespan opens (runtime_support.py)."""
    patch_stores(monkeypatch)
