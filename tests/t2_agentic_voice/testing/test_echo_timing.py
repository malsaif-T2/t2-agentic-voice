"""The time of each step of an echo call (testing/echo_timing.py). Plan 003's Track H builds it and
replaces this file's stub test with its own."""

from __future__ import annotations

from typing import cast

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.testing.echo_timing import EchoTiming, TurnTiming, echo_timings


def test_echo_timings_is_a_stub_until_track_h(settings: VoiceSettings) -> None:
    with pytest.raises(NotImplementedError, match="Track H"):
        echo_timings(
            [(AudioClip(pcm16=b"\x00\x00" * 16_000), "en")],
            agent=VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")]),
            settings=settings,
            stt=cast(SpeechToText, object()),
            tts=cast(TextToSpeech, object()),
            lead_s=1.0,
            tail_s=4.5,
        )
    timing = EchoTiming(turns=(TurnTiming(end_ms=1000.0),), usage=())
    assert (timing.turns[0].end_ms, timing.turns[0].stt_sent_ms) == (1000.0, None)
