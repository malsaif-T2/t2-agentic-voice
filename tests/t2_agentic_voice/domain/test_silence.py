"""Text from silence (domain/silence.py): `from_silence` is a stub, and the caption list empty,
until plan 005's Track A builds the filter from the prototype's list and rule F's threshold."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.silence import CAPTIONS, from_silence


def test_from_silence_is_a_stub_until_the_filter_is_built() -> None:
    assert CAPTIONS == ()
    with pytest.raises(NotImplementedError, match="Track A"):
        from_silence("made-up words", 0.9, no_speech_max=0.5, captions=CAPTIONS)
