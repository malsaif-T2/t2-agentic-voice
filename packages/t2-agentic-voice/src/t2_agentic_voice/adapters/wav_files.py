"""The WAV files the caches keep (the phrase cache, adapters/phrase_cache.py, and the clause cache,
adapters/clause_cache.py): a take written as a WAV file, mono and 16-bit at its sample rate
(`wav_of`); read back only when it reads as one of those, its frames all there (`take_of`); and
written whole, to a temporary name beside it and then renamed onto it (`write_whole`), so a
stopped write leaves no half file under the real name.
"""

from __future__ import annotations

import io
import secrets
import wave
from pathlib import Path

from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk


def wav_of(audio: AudioChunk) -> bytes:
    """`audio` as a WAV file: mono, 16-bit, at its sample rate."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(audio.sample_rate)
        writer.writeframes(audio.pcm16)
    return buffer.getvalue()


def take_of(data: bytes) -> AudioChunk | None:
    """The audio of `data`, a WAV file as `wav_of` writes one: mono, 16-bit, with as many frames
    as its header counts; None for anything else (another layout, a cut file, no WAV)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            if (reader.getnchannels(), reader.getsampwidth()) != (1, 2):
                return None
            frames = reader.getnframes()
            rate, pcm = reader.getframerate(), reader.readframes(frames)
        if len(pcm) != 2 * frames:
            return None
        return AudioChunk(pcm16=pcm, sample_rate=rate)
    except (wave.Error, EOFError, ValueError):  # ValueError: pydantic's, on a bad rate
        return None


def write_whole(path: Path, data: bytes) -> None:
    """Write `data` to `path` whole: to `<stem>.<random>.part` beside it, then renamed onto it;
    the temporary file is removed however the write ends. An OSError of the disk's is raised."""
    part = path.with_name(f"{path.stem}.{secrets.token_hex(8)}.part")
    try:
        part.write_bytes(data)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
