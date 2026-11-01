"""The checks of the run's worktree.

Plan 002's Track E builds them and replaces this file's stub test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.worktree import run_commit


def test_the_worktree_checks_are_stubs_until_track_e(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track E"):
        run_commit(tmp_path)
