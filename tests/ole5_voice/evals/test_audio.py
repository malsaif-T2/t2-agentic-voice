"""The golden set's audio files: 16 kHz mono 16-bit WAV in and out, hashed, checked and cut,
with the standard library's `wave`. Every clip here is made up, in memory or in tmp_path."""

from __future__ import annotations

import contextlib
import hashlib
import io
import struct
import wave
from pathlib import Path

import pytest
from ole5_voice.evals.audio import (
    AudioFormatError,
    leading_window,
    parse_wav,
    read_wav,
    sha256_file,
    sha256_of,
    write_wav,
)


def _pcm(samples: int) -> bytes:
    """A made-up ramp of 16-bit samples, so a wrong byte order or offset shows."""
    return b"".join(struct.pack("<h", (i * 97) % 4096 - 2048) for i in range(samples))


def _wav(channels: int, width: int, rate: int, frames: int = 160) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x01" * channels * width * frames)
    return buffer.getvalue()


def test_a_wav_round_trips_with_its_hash_and_length(tmp_path: Path) -> None:
    pcm = _pcm(16_000)
    data = write_wav(pcm)
    path = tmp_path / "take.wav"
    path.write_bytes(data)
    wav = read_wav(path)
    assert (wav.pcm16, wav.sample_rate, wav.frames) == (pcm, 16_000, 16_000)
    assert (wav.seconds, wav.milliseconds) == (1.0, 1000)
    assert wav.sha256 == hashlib.sha256(data).hexdigest() == sha256_file(path) == sha256_of(data)


@pytest.mark.parametrize(
    ("channels", "width", "rate"),
    [(2, 2, 16_000), (1, 1, 16_000), (1, 3, 16_000), (1, 2, 44_100), (1, 2, 8_000)],
)
def test_any_other_format_is_refused(channels: int, width: int, rate: int) -> None:
    with pytest.raises(AudioFormatError, match="16000 Hz, mono, 16-bit"):
        parse_wav(_wav(channels, width, rate))


@pytest.mark.parametrize("data", [b"", b"RIFF", b"not a wav file at all, only text"])
def test_bytes_that_are_not_a_wav_are_refused(data: bytes) -> None:
    with pytest.raises(AudioFormatError, match="not a PCM WAV file"):
        parse_wav(data)


def test_a_file_cut_short_is_refused() -> None:
    data = write_wav(_pcm(1_600))
    with pytest.raises(AudioFormatError, match="cut short"):
        parse_wav(data[:-100])


def _chunk(name: bytes, body: bytes, size: int | None = None) -> bytes:
    return name + struct.pack("<I", len(body) if size is None else size) + body


def _riff(*chunks: bytes) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


FMT = struct.pack("<HHIIHH", 1, 1, 16_000, 32_000, 2, 16)  # PCM, mono, 16 kHz, 16-bit


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        # A chunk whose size runs past the RIFF chunk's end: `wave` raises a bare RuntimeError.
        (_riff(_chunk(b"LIST", b"INFO", 0x7FFF_FFFF), _chunk(b"fmt ", FMT)), "claims more"),
        (_riff(_chunk(b"fmt ", FMT, 0x7FFF_FFFF), _chunk(b"data", b"\x00\x00")), "claims more"),
        (_riff(_chunk(b"fmt ", FMT), _chunk(b"data", b"\x00\x00", 0xFFFF_FFFF)), "cut short"),
        (_riff(_chunk(b"fmt ", FMT), _chunk(b"data", b"")), "no samples"),
        (write_wav(b""), "no samples"),
    ],
    ids=["LIST past the end", "fmt past the end", "data of 4 GB", "data of 0", "written empty"],
)
def test_a_hostile_or_empty_header_is_refused(data: bytes, problem: str) -> None:
    """The recorder refuses a posted take with `parse_wav`: nothing but AudioFormatError comes
    out of it, whatever the header claims."""
    with pytest.raises(AudioFormatError, match=problem):
        parse_wav(data)


def test_random_damage_to_a_header_raises_nothing_but_a_format_error() -> None:
    """A fixed sample of single-byte changes to the header and first chunk sizes."""
    good = write_wav(_pcm(160))
    for offset in range(44):
        for value in (0x00, 0x7F, 0xFF):
            damaged = good[:offset] + bytes([value]) + good[offset + 1 :]
            with contextlib.suppress(AudioFormatError):
                parse_wav(damaged)


def test_a_leading_window_is_cut_from_the_start() -> None:
    wav = parse_wav(write_wav(_pcm(16_000)))
    assert leading_window(wav, 500) == wav.pcm16[: 8_000 * 2]
    assert len(leading_window(wav, 1)) == 16 * 2
    assert leading_window(wav, 2_000) == wav.pcm16  # longer than the clip: the whole clip
    with pytest.raises(ValueError, match="at least 1 ms"):
        leading_window(wav, 0)


def test_half_a_sample_is_never_written() -> None:
    with pytest.raises(ValueError, match="whole 16-bit samples"):
        write_wav(b"\x00")
