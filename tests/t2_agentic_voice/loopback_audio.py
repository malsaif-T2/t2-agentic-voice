"""The audio of the loopback checks (loopback_support.py; TD-087), all generated, no audio file
(tests/ole5_voice/evals/test_no_audio.py): the caller's microphone (`Signal`, a sine the fakes'
tone detector hears as speech), the fakes' text-to-speech saying the heard words at a pitch of
their own (`PitchedSpeech`), and how a frame of the agent's audio is heard (`pitch`).
"""

from __future__ import annotations

import math
import struct
from collections.abc import AsyncIterator, Collection
from itertools import pairwise
from typing import Any, Protocol, cast

from aiortc.mediastreams import AudioStreamTrack
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.t2_agentic_voice.fakes import FakeTextToSpeech

SECONDS_PER_CHAR = 0.03
# The phrases, the heard words and the caller's signal, each at a pitch of its own.
PHRASE_HZ, HEARD_HZ, SIGNAL_HZ = 400.0, 1000.0, 300.0
AMPLITUDE = 8000
# A frame of the agent's audio is heard when a sample passes LOUD, at the frequency its zero
# crossings give, within BIN_HZ (two crossings in a 20 ms frame).
LOUD, BIN_HZ = 1000, 50.0


class _Plane(Protocol):
    def update(self, input: bytes) -> None: ...
    def __bytes__(self) -> bytes: ...


class _Format(Protocol):
    is_planar: bool


class _Layout(Protocol):
    nb_channels: int


class Frame(Protocol):
    """PyAV's audio frame, as these checks use it: PyAV comes with aiortc, and only the packages
    a project declares are imported (ARCH-DEPS)."""

    planes: tuple[_Plane, ...]
    samples: int
    sample_rate: int
    pts: int | None
    format: _Format
    layout: _Layout


def sine(hz: float, samples: int, rate: int, start: int = 0) -> bytes:
    """`samples` of a sine at `hz` as mono PCM16 at `rate`, from sample `start`."""
    values = (
        round(AMPLITUDE * math.sin(2 * math.pi * hz * (start + n) / rate)) for n in range(samples)
    )
    return struct.pack(f"<{samples}h", *values)


class PitchedSpeech(FakeTextToSpeech):
    """The fakes' text-to-speech, saying each text as a sine: each text of `heard` at HEARD_HZ
    and every other text, the phrases the cache declares, at PHRASE_HZ."""

    def __init__(self, heard: Collection[str]) -> None:
        super().__init__(seconds_per_char=SECONDS_PER_CHAR)
        self.heard = heard

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, language))
        hz = HEARD_HZ if text in self.heard else PHRASE_HZ
        rate = self.sample_rate
        pcm = sine(hz, round(len(text) * self.seconds_per_char * rate), rate)
        step = round(self.chunk_s * rate) * 2
        for i in range(0, len(pcm), step):
            yield AudioChunk(pcm16=pcm[i : i + step], sample_rate=rate)


class Signal(AudioStreamTrack):
    """The caller's microphone: aiortc's silent track (20 ms frames of mono PCM16, paced in
    real time), the sine in place of its silence while `say` asks for it."""

    def __init__(self) -> None:
        super().__init__()
        self._sent = 0
        self._loud_s = 0.0

    def say(self, seconds: float) -> None:
        self._loud_s = seconds

    async def recv(self) -> Any:  # a PyAV frame
        frame = cast(Frame, await super().recv())
        loud = min(frame.samples, round(self._loud_s * frame.sample_rate))
        if loud:
            self._loud_s -= loud / frame.sample_rate
            silence = bytes(2 * (frame.samples - loud))
            frame.planes[0].update(sine(SIGNAL_HZ, loud, frame.sample_rate, self._sent) + silence)
        self._sent += frame.samples
        return frame


def pitch(frame: Frame) -> float | None:
    """The frequency of the frame's first channel, from its zero crossings, in Hz; None for a
    quiet frame."""
    channels = 1 if frame.format.is_planar else frame.layout.nb_channels
    # A plane's buffer may run past its samples (FFmpeg pads it): the samples come first.
    whole = memoryview(bytes(frame.planes[0])).cast("h")
    first = whole[: frame.samples * channels : channels].tolist()
    if not first or max(abs(sample) for sample in first) < LOUD:
        return None
    crossings = sum((a < 0) != (b < 0) for a, b in pairwise(first))
    return crossings / 2 * frame.sample_rate / len(first)
