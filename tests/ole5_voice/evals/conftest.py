"""Fixtures the golden set's tests share; the suite's own are in `tests/conftest.py`."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import structlog
from t2_agentic_voice import configure_logging

from tests.ole5_voice.evals.recorder_support import Tree, make_tree
from tests.ole5_voice.evals.run_support import World, make_world

# The time stamp the library's logging gives a line (UTC, ISO 8601), then its level.
_LIBRARY_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z \[")


def _library_line(out: str, event: str) -> str:
    (line,) = [line for line in out.splitlines() if event in line]
    assert _LIBRARY_TIME.match(line), line
    return line


@pytest.fixture
def new_process_logs() -> Iterator[Callable[[str, str], str]]:
    """Logging as a new process finds it, with nothing configured (structlog's own defaults, in
    local time), for a test that a command configures logging before it logs (plan 004, app7).
    It gives the check: the one line of an event in the output, which must be stamped as the
    library stamps. The library's console defaults are set again after."""
    structlog.reset_defaults()
    try:
        yield _library_line
    finally:
        configure_logging("INFO", "console")


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    """A made-up tree like the owner's, for the recorder (`recorder_support.make_tree`)."""
    return make_tree(tmp_path)


@pytest.fixture
def world(tmp_path: Path) -> World:
    """A run's checkout, worktree and audio root (`run_support.make_world`)."""
    return make_world(tmp_path)
