"""The matcher.

Plan 002's Track D builds it and replaces this file's stub test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.matcher import load_matcher


def test_the_matcher_is_a_stub_until_track_d(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track D"):
        load_matcher(tmp_path / "spelling.toml")
