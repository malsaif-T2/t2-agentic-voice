"""The answerers.

Plan 002's Track E builds them and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals.answerers import make_answerer
from t2_agentic_voice import Settings


def test_the_answerers_are_stubs_until_track_e(settings: Settings) -> None:
    with pytest.raises(NotImplementedError, match="Track E"):
        make_answerer("reference", settings)
