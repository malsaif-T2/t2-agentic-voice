"""Speaking numbers and IDs (domain/text/speaking.py). Plan 003's Track A builds them and replaces
this file's stub test with its own."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from t2_agentic_voice.domain.text.speaking import speak_digits, speak_id, speak_number


def test_speaking_is_a_stub_until_track_a() -> None:
    calls: list[Callable[[], object]] = [
        lambda: speak_number(3, language="en"),
        lambda: speak_id("0451", language="ar"),
        lambda: speak_digits("made-up words 12", language="ar-SA"),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track A"):
            call()
