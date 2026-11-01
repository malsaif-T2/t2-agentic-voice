"""`poe eval-compare`.

Plan 002's Track F builds it and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals import compare


def test_eval_compare_is_a_stub_until_track_f() -> None:
    with pytest.raises(NotImplementedError, match="Track F"):
        compare.main([])
