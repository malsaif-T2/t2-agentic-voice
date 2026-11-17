"""Whether a piece of the agent's audio is audible (turn_book.py's time to first audio, TD-090;
testing/timed_speech.py's and turn_replay.py's first sound)."""

from __future__ import annotations

import struct

# The loudest a 16-bit sample of the agent's audio may be and still be silence: about -40 dBFS
# (328 of 32768), the agent's value, below the quietest speech and above a model's dither; also
# testing/timed_speech.py's `NOISE_FLOOR`, for a take's first sound.
AUDIBLE_FLOOR = 328


def audible(pcm16: bytes) -> bool:
    """Whether `pcm16` (mono, 16-bit little-endian) holds a sample louder than AUDIBLE_FLOOR."""
    whole = pcm16[: len(pcm16) - len(pcm16) % 2]
    return any(abs(value) > AUDIBLE_FLOOR for (value,) in struct.iter_unpack("<h", whole))
