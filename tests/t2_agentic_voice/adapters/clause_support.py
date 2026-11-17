"""What the clause cache's tests share (test_clause_cache.py, test_clause_cache_files.py): a cache
over a fake text-to-speech in a test's own folder, a clause said through it and its take kept,
the take a fake gives for a text, a few odd fakes, and the read limit the tests read takes
within. Nothing here reads `var/`."""

from __future__ import annotations

import io
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from t2_agentic_voice.adapters.clause_cache import ClauseCache
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsSettings, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

from tests.t2_agentic_voice.fakes import FakeTextToSpeech, tone

VOICES = TtsSettings(provider="groq").languages  # a model and a voice a language
# Far past any read of a take, however loaded the machine: the clause cache's own limit
# (`READ_TIMEOUT_S`, 0.1 s) turns a read that a busy machine delays into a miss
# (conftest.py's `relaxed_reads`).
RELAXED_READ_S = 30.0
TEXT = "Your request is open, and we will call you back today."


def cache_of(
    tts: TextToSpeech,
    folder: Path,
    *,
    voices: dict[LanguageTag, TtsVoice] | None = None,
    trim_silence: bool = False,
    max_mb: int = 512,
) -> ClauseCache:
    """A clause cache over `tts` in `folder`, the default voices unless given."""
    return ClauseCache(
        tts,
        folder=folder,
        voices=VOICES if voices is None else voices,
        trim_silence=trim_silence,
        max_mb=max_mb,
    )


async def said(cache: ClauseCache, text: str = TEXT, language: str = "en") -> list[AudioChunk]:
    """Every chunk `cache` gives for `text`, as the bridge reads a request."""
    return [chunk async for chunk in cache.synthesize(text, language=language)]


async def kept(cache: ClauseCache, text: str = TEXT, language: str = "en") -> list[AudioChunk]:
    """`text` said through `cache`, and its writer let finish what it was given."""
    chunks = await said(cache, text, language)
    await cache._written()
    return chunks


def take(text: str, fake: FakeTextToSpeech) -> bytes:
    """What `fake` says for `text`, whole."""
    return tone(len(text) * fake.seconds_per_char, fake.sample_rate)


def takes_in(folder: Path) -> list[Path]:
    """The takes' files in `folder`: each `<key>.wav`."""
    return sorted(path for path in folder.iterdir() if path.suffix == ".wav")


def wav(pcm: bytes, *, channels: int = 1, width: int = 2, rate: int = 24_000) -> bytes:
    """`pcm` as a WAV file of `channels` and `width` bytes a sample."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(pcm)
    return buffer.getvalue()


class OddSpeech(FakeTextToSpeech):
    """The fakes' text-to-speech with odd takes: `half` fails after its first chunk, `two
    rates` streams at two sample rates; every other text as the fakes say it."""

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        if text == "half":
            self.calls.append((text, language))
            yield AudioChunk(pcm16=tone(0.2, 24_000), sample_rate=24_000)
            raise ProviderError("connection_lost", True)
        if text == "two rates":
            self.calls.append((text, language))
            yield AudioChunk(pcm16=tone(0.2, 24_000), sample_rate=24_000)
            yield AudioChunk(pcm16=tone(0.2, 16_000), sample_rate=16_000)
            return
        async for chunk in super().synthesize(text, language=language):
            yield chunk


class OtherSpeech(FakeTextToSpeech):
    """The fakes' text-to-speech under another adapter's name."""

    name = "other"
