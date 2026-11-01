"""`poe eval`.

Plan 002's Track E builds it and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals import run


def test_eval_is_a_stub_until_track_e() -> None:
    with pytest.raises(NotImplementedError, match="Track E"):
        run.main([])
