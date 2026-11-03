"""The text-to-speech port's types (the design's 6.1), and a provider that implements it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

FLOW = DataFlow(
    provider="Example", processed_in="not stated", stored_in="nowhere", retention="none"
)


class _Beeps:
    """A provider that says each character as 10 ms of one sample value, in two chunks: the
    first with its headroom, the last flagging a take cut short when the text ends in `~`."""

    name = "beeps"
    data_flow = FLOW

    def __init__(self) -> None:
        self.closed = False

    def max_chars(self, language: str) -> int | None:
        return 20 if language == "en" else None

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        samples = b"\x01\x00" * 80 * len(text)  # 10 ms of 8 kHz audio per character
        yield AudioChunk(pcm16=samples, sample_rate=8000, remaining_requests=99)
        yield AudioChunk(pcm16=b"", sample_rate=8000, cut_short=text.endswith("~"))

    async def check_language(self, language: str) -> None:
        if language not in ("ar-SA", "ar", "en"):
            raise ConfigurationError(f"No voice for {language}. FIX: add one to tts.languages.")

    async def aclose(self) -> None:
        self.closed = True


def test_a_chunk_knows_how_long_it_plays_and_may_be_empty() -> None:
    chunk = AudioChunk(pcm16=b"\x00\x00" * 12_000, sample_rate=24_000)
    assert (chunk.seconds, chunk.remaining_requests, chunk.cut_short) == (0.5, None, False)
    assert AudioChunk(pcm16=b"", sample_rate=24_000, cut_short=True).seconds == 0


def test_a_chunk_holds_whole_samples_at_a_real_rate_and_no_negative_headroom() -> None:
    with pytest.raises(ValidationError, match="even number of bytes"):
        AudioChunk(pcm16=b"\x00", sample_rate=24_000)
    for bad in ({"sample_rate": 0}, {"remaining_requests": -1}, {"remaining_tokens": -1}):
        with pytest.raises(ValidationError):
            AudioChunk.model_validate({"pcm16": b"", "sample_rate": 24_000} | bad)
    with pytest.raises(ValidationError):
        AudioChunk.model_validate({"pcm16": b"", "sample_rate": 24_000, "voice": "troy"})


def test_a_provider_implements_the_port() -> None:
    beeps = _Beeps()
    tts: TextToSpeech = beeps

    async def speak(text: str) -> list[AudioChunk]:
        return [chunk async for chunk in tts.synthesize(text, language="en")]

    chunks = asyncio.run(speak("hi~"))
    assert [c.seconds for c in chunks] == [0.03, 0.0]
    assert [(c.remaining_requests, c.cut_short) for c in chunks] == [(99, False), (None, True)]
    assert (tts.max_chars("en"), tts.max_chars("ar"), tts.name) == (20, None, "beeps")
    asyncio.run(tts.check_language("ar-SA"))
    with pytest.raises(ConfigurationError, match="FIX"):
        asyncio.run(tts.check_language("fr"))
    asyncio.run(tts.aclose())
    assert beeps.closed
