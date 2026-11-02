"""The golden set's audio files: WAV, 16 kHz, mono, 16-bit PCM, read and written with the
standard library's `wave`, so no audio package is installed.

`poe golden` hashes and checks the files it is given, the runner cuts its clips and windows
from them (`run_parts.py`, `answerers.py`), and the recorder writes its takes with them
(`recorder_state.py`). The files stay out of git (D-022); a manifest holds each one's hash,
length and format.
"""

from __future__ import annotations

import hashlib
import io
import wave
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes a sample: 16-bit


class AudioFormatError(ValueError):
    """A file that is not a 16 kHz mono 16-bit PCM WAV, one that is cut short or whose header
    lies about a chunk's size, or one that holds no samples."""


class Wav(BaseModel):
    """One WAV file's samples, and the SHA-256 of the whole file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pcm16: bytes
    sample_rate: int = Field(gt=0)
    sha256: str

    @property
    def frames(self) -> int:
        return len(self.pcm16) // SAMPLE_WIDTH

    @property
    def seconds(self) -> float:
        return self.frames / self.sample_rate

    @property
    def milliseconds(self) -> int:
        """Its length in whole milliseconds, rounded down, for comparing with a window."""
        return self.frames * 1000 // self.sample_rate


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file, read in chunks, so a long recording is never held whole."""
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def parse_wav(data: bytes) -> Wav:
    """The samples of a WAV file's bytes; AudioFormatError, and no other exception, when it is
    not 16 kHz mono 16-bit PCM, holds fewer samples than its header says, has a chunk that
    claims more bytes than the file holds, or holds no samples at all. The recorder refuses a
    take with it, so a crafted or corrupt file is refused, never raised past it."""
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            channels, width = reader.getnchannels(), reader.getsampwidth()
            rate, frames = reader.getframerate(), reader.getnframes()
            pcm = reader.readframes(frames)
    except (wave.Error, EOFError) as error:
        raise AudioFormatError(f"not a PCM WAV file ({error})") from None
    except RuntimeError:  # `wave` seeking past the RIFF chunk's end, raised with no message
        raise AudioFormatError(
            "not a PCM WAV file (a chunk claims more bytes than the file holds)"
        ) from None
    if (rate, channels, width) != (SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH):
        raise AudioFormatError(
            f"{rate} Hz, {channels} channel(s), {8 * width}-bit: the golden set's audio is "
            f"{SAMPLE_RATE} Hz, mono, 16-bit"
        )
    if len(pcm) != frames * SAMPLE_WIDTH:
        raise AudioFormatError(
            f"cut short: {len(pcm)} bytes of samples where the header says {frames * SAMPLE_WIDTH}"
        )
    if not frames:
        raise AudioFormatError("holds no samples")
    return Wav(pcm16=pcm, sample_rate=rate, sha256=sha256_of(data))


def read_wav(path: Path) -> Wav:
    """`parse_wav` of a file."""
    return parse_wav(path.read_bytes())


def write_wav(pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """The bytes of a mono 16-bit WAV file holding `pcm16`."""
    if len(pcm16) % SAMPLE_WIDTH:
        raise ValueError("pcm16 holds whole 16-bit samples: an even number of bytes")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(SAMPLE_WIDTH)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm16)
    return buffer.getvalue()


def leading_window(wav: Wav, ms: int) -> bytes:
    """The samples of the first `ms` milliseconds (rounded down to whole samples); the whole
    clip when it is shorter."""
    if ms <= 0:
        raise ValueError("a window lasts at least 1 ms")
    frames = wav.sample_rate * ms // 1000
    return wav.pcm16[: frames * SAMPLE_WIDTH]
