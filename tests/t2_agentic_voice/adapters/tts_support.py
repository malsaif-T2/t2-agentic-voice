"""What the text-to-speech tests share (test_wav_stream.py, test_groq_tts.py): WAV streams built
by hand as Orpheus streams them, a header with a `LIST` chunk before the audio and a `data` size
that is not the audio's, and the sounds they hold. Nothing here is a golden-set item's."""

from __future__ import annotations

import struct

# A streamed WAV's `data` size: unknown when the header is sent, so not the audio's.
STREAMED = 0xFFFFFFFF
# Orpheus's header carries a LIST chunk before its audio; this one has an odd size, so a pad byte.
LIST = (b"LIST", b"INFOISFT\x05\x00\x00\x00made\x00")


def silence(seconds: float, rate: int = 24_000) -> bytes:
    """`seconds` of digital silence, mono PCM16 at `rate`."""
    return b"\x00\x00" * round(seconds * rate)


def tone(seconds: float, rate: int = 24_000, level: int = 1024) -> bytes:
    """`seconds` of a square tone at half the sample rate, `level` loud (1024 is about -30 dBFS:
    speech; 100, about -50 dBFS, a hiss under the silence floor)."""
    pair = struct.pack("<hh", level, -level)
    samples = round(seconds * rate)
    return (pair * (samples // 2 + 1))[: samples * 2]


def wav(
    pcm: bytes,
    *,
    rate: int = 24_000,
    channels: int = 1,
    bits: int = 16,
    tag: int = 1,
    chunks: tuple[tuple[bytes, bytes], ...] = (LIST,),
    data_size: int = STREAMED,
    fmt_extra: bytes = b"",
) -> bytes:
    """A WAV as a stream sends it: RIFF, its `fmt ` chunk, `chunks` (each padded to an even
    size), then the `data` chunk's head with `data_size`, then `pcm`."""
    align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", tag, channels, rate, rate * align, align, bits) + fmt_extra
    body = b"WAVE" + _chunk(b"fmt ", fmt)
    for kind, data in chunks:
        body += _chunk(kind, data)
    body += b"data" + struct.pack("<I", data_size) + pcm
    return b"RIFF" + struct.pack("<I", STREAMED) + body


def _chunk(kind: bytes, data: bytes) -> bytes:
    return kind + struct.pack("<I", len(data)) + data + b"\x00" * (len(data) % 2)


def pieces(data: bytes, size: int) -> list[bytes]:
    """`data` cut every `size` bytes, as a network may cut it."""
    return [data[i : i + size] for i in range(0, len(data), size)]
