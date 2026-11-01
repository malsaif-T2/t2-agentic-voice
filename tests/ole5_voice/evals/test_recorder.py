"""`poe record`.

Plan 002's Track G builds it and replaces this file's stub test.
"""

from __future__ import annotations

import pytest
from ole5_voice.evals import recorder


def test_record_is_a_stub_until_track_g() -> None:
    with pytest.raises(NotImplementedError, match="Track G"):
        recorder.main([])
