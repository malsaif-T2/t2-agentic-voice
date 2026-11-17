"""Fixtures the golden set's tests share; the suite's own are in `tests/conftest.py`."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from t2_agentic_voice import TtsSettings, VoiceSettings

from tests.ole5_voice.evals.recorder_support import Tree, make_tree
from tests.ole5_voice.evals.run_support import World, make_world

# The time stamp the library's logging gives a line (UTC, ISO 8601), then its level.
_LIBRARY_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z \[")


def _library_line(out: str, event: str) -> str:
    (line,) = [line for line in out.splitlines() if event in line]
    assert _LIBRARY_TIME.match(line), line
    return line


@pytest.fixture
def new_process_logs(unconfigured_logging: None) -> Callable[[str, str], str]:
    """Logging as a new process finds it, with nothing configured (a line logged before the
    command configures logging reaches no output), for a test that a command configures logging
    before it logs (plan 004, app7). It gives the check: the one line of an event in the output,
    which must be stamped as the library stamps. tests/conftest.py undoes it after."""
    return _library_line


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    """A made-up tree like the owner's, for the recorder (`recorder_support.make_tree`)."""
    return make_tree(tmp_path)


@pytest.fixture
def world(tmp_path: Path) -> World:
    """A run's checkout, worktree and audio root (`run_support.make_world`)."""
    return make_world(tmp_path)


@pytest.fixture
def settings(settings: VoiceSettings) -> VoiceSettings:
    """The suite's settings with Groq's Orpheus speaking, as Ole5's registered runs do whatever
    `tts.provider` names (run_settings.load_settings; D-114 made ElevenLabs the default)."""
    return settings.model_copy(update={"tts": TtsSettings(provider="groq")})
