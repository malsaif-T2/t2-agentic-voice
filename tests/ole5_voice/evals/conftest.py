"""Fixtures the golden set's tests share; the suite's own are in `tests/conftest.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from t2_agentic_voice import configure_logging

from tests.ole5_voice.evals.run_support import World, make_world


@pytest.fixture
def plain_logs() -> None:
    """Log lines read as plain text, whatever ran before: for a test that reads what is logged
    by code that does not configure logging itself (a module marks it with `usefixtures`)."""
    configure_logging("INFO", "console")


@pytest.fixture
def world(tmp_path: Path) -> World:
    """A run's checkout, worktree and audio root (`run_support.make_world`)."""
    return make_world(tmp_path)
