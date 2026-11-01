"""The speech-to-text port's types (the design's 6.1), and a provider that implements it."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from t2_agentic_voice.domain.ports.speech_to_text import (
    AudioClip,
    DataFlow,
    SpeechToText,
    Transcript,
)

FLOW = DataFlow(
    provider="Example", processed_in="not stated", stored_in="nowhere", retention="none"
)


class _Length:
    """A provider that hears only how long the clip is."""

    name = "length"
    data_flow = FLOW

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        return Transcript(
            text=f"{clip.seconds:.1f} s", language=language, billed_seconds=clip.seconds
        )


def test_a_clip_knows_how_long_it_lasts() -> None:
    clip = AudioClip(pcm16=b"\x00\x00" * 8000)
    assert (clip.sample_rate, clip.seconds) == (16_000, 0.5)
    assert AudioClip(pcm16=b"\x01\x00" * 800, sample_rate=8000).seconds == 0.1


def test_a_clip_holds_whole_samples_at_a_real_rate() -> None:
    with pytest.raises(ValidationError, match="even number of bytes"):
        AudioClip(pcm16=b"\x00")
    with pytest.raises(ValidationError):
        AudioClip(pcm16=b"", sample_rate=0)


def test_a_transcript_keeps_the_no_speech_estimate_within_bounds() -> None:
    heard = Transcript(text="", language="ar", no_speech_prob=0.9, billed_seconds=10)
    assert (heard.no_speech_prob, heard.confidence, heard.billed_seconds) == (0.9, None, 10.0)
    with pytest.raises(ValidationError):
        Transcript(text="", language=None, no_speech_prob=1.5)
    with pytest.raises(ValidationError):
        Transcript(text="", language=None, billed_seconds=-1)


def test_a_provider_implements_the_port() -> None:
    stt: SpeechToText = _Length()
    clip = AudioClip(pcm16=b"\x00\x00" * 1600)
    heard = asyncio.run(stt.transcribe(clip, language="ar", prompt=None))
    assert (heard.text, heard.language, heard.billed_seconds) == ("0.1 s", "ar", 0.1)
    assert (stt.name, stt.data_flow.provider) == ("length", "Example")
