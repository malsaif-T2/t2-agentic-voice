"""The scorecard.

Plan 002's Track F builds it and replaces this file's stub test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.scorecard import write_scorecard

from tests.ole5_voice.evals import samples


def test_the_scorecard_is_a_stub_until_track_f(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track F"):
        write_scorecard(samples.run(), [], complete=True, out=tmp_path)
