"""The pronunciation map (domain/text/pronounce.py). Plan 003's Track A builds it and replaces this
file's stub test with its own."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce


def test_the_pronunciation_map_is_a_stub_until_track_a() -> None:
    entries: Pronunciations = {"LT-": {"en": "L T"}}
    with pytest.raises(NotImplementedError, match="Track A"):
        pronounce("Made-up LT- words", entries, language="en")
