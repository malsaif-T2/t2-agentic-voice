"""The held-out split.

Plan 002's Track D builds it and replaces this file's stub tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import split


def test_the_split_is_a_stub_until_track_d(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track D"):
        split.split_items([], salt="made-up")
    with pytest.raises(NotImplementedError, match="Track D"):
        split.load_split(tmp_path / "split.json")
    with pytest.raises(NotImplementedError, match="Track D"):
        split.main([])
