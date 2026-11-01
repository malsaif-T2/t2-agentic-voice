"""The window metrics.

Plan 002's Track E builds them and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals.windows import leading_words


def test_the_window_metrics_are_stubs_until_track_e() -> None:
    with pytest.raises(NotImplementedError, match="Track E"):
        leading_words("stop now", "stop")
