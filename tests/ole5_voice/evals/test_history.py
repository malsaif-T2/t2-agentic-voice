"""The run history and `poe eval-history`.

Plan 002's Track F builds them and replaces this file's stub tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import history

from tests.ole5_voice.evals import samples


def test_the_history_is_a_stub_until_track_f(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track F"):
        history.append_line(samples.history_line(), tmp_path / "history.jsonl")
    with pytest.raises(NotImplementedError, match="Track F"):
        history.main([])
