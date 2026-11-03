"""The heard words' audio as the text-to-speech gives it, read on its way to the pipeline:
`TimedSpeech` wraps a `TextToSpeech` and keeps, for each request, when its first sound came and
how much audio came before it (`echo_timing.py`'s `heard_sound_ms` and `leading_silence_ms`),
handing every chunk on unchanged.
"""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass

from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock

# The loudest a 16-bit sample may be and still count as the silence before speech: about
# -40 dBFS (328 of 32768), the agent's value, below the quietest speech and above a model's
# dither; a take's first sound is its first sample louder than this.
NOISE_FLOOR = 328


def first_sound(pcm16: bytes) -> int | None:
    """The index of the first sample of `pcm16` (mono, 16-bit little-endian) louder than
    `NOISE_FLOOR`; None when there is none."""
    samples = struct.iter_unpack("<h", pcm16)
    return next((i for i, (value,) in enumerate(samples) if abs(value) > NOISE_FLOOR), None)


@dataclass
class Take:
    """One text-to-speech request as the provider answered it: its text and language; when, on
    the call's clock, the chunk holding its first sound came; and how many seconds of its audio
    came before that sound. Both are None while no sound has come."""

    text: str
    language: str
    first_sound_at: float | None = None
    leading_silence_s: float | None = None


class TimedSpeech:
    """A `TextToSpeech` that hands on `inner`'s audio unchanged, keeping each request's `Take`
    in `takes`, in the order they were sent; its close closes `inner`."""

    def __init__(self, inner: TextToSpeech, clock: Clock = SYSTEM_CLOCK) -> None:
        self.inner, self.clock = inner, clock
        self.name, self.data_flow = inner.name, inner.data_flow
        self.takes: list[Take] = []

    def max_chars(self, language: str) -> int | None:
        return self.inner.max_chars(language)

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        take = Take(text=text, language=language)
        self.takes.append(take)
        before = 0  # the take's samples before this chunk
        stream = self.inner.synthesize(text, language=language)
        try:
            async for chunk in stream:
                if take.first_sound_at is None:
                    index = first_sound(chunk.pcm16)
                    if index is not None:
                        take.first_sound_at = self.clock.now()
                        take.leading_silence_s = (before + index) / chunk.sample_rate
                    before += len(chunk.pcm16) // 2
                yield chunk
        finally:  # a cancel or an early close closes the provider's stream too
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    async def check_language(self, language: str) -> None:
        await self.inner.check_language(language)

    async def aclose(self) -> None:
        await self.inner.aclose()
