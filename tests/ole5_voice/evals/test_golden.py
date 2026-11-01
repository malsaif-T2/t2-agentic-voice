"""`poe golden`.

Plan 002's Track D builds it and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals import golden


def test_golden_is_a_stub_until_track_d() -> None:
    with pytest.raises(NotImplementedError, match="Track D"):
        golden.main([])
