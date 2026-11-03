"""Where a call's turns end (testing/turns.py). Plan 003's Track H builds it and replaces this
file's stub test with its own."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.testing.turns import TurnEnd, turn_ends


def test_turn_ends_is_a_stub_until_track_h(settings: VoiceSettings) -> None:
    clips = [AudioClip(pcm16=b"\x00\x00" * 16_000)]
    with pytest.raises(NotImplementedError, match="Track H"):
        turn_ends(clips, settings=settings, lead_s=1.0, tail_s=4.5)
    assert TurnEnd(speech_stop_ms=800.0, end_ms=1000.0).end_ms == 1000.0
