"""What the text-to-speech adapters of the providers measured beside Groq share (D-114): a take
of raw PCM read as it streams in, chunk by chunk, as the Groq adapter reads its WAV.

- `PcmTake`: raw mono 16-bit little-endian PCM at the rate the request asked the provider for
  (a raw stream carries no header to read it from, so the rate is the request's own, never a
  guess), read through `WavStream` behind a header of that rate, so the silence measure, the
  trim of `tts.trim_silence` and the whole-sample rule are the Groq adapter's own. `feed` gives
  each piece's whole samples, the first chunk carrying no headroom (these providers report none
  per request), and `last` the take's closing chunk: its held audio, and `cut_short` by the Groq
  adapter's rule (`groq_tts.cut_short`), or an empty one when the take gave no audio at all.
- `too_long`, `no_voice`: the refusals every adapter makes unsent.
"""

from __future__ import annotations

import struct
from typing import Final

from t2_agentic_voice.adapters.groq_tts import cut_short
from t2_agentic_voice.adapters.wav_stream import WavStream
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

# A streamed WAV's `data` size, unknown when its header is made (as Orpheus sends it).
_STREAMED: Final = 0xFFFFFFFF


def _header(rate: int) -> bytes:
    """A mono 16-bit PCM WAV's header at `rate`, its `data` size unknown."""
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (
        b"RIFF"
        + struct.pack("<I", _STREAMED)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", _STREAMED)
    )


class PcmTake:
    """One take of raw PCM at `rate` (the module's docstring); `trim` drops the silence before
    the speech, as `tts.trim_silence` asks."""

    def __init__(self, *, rate: int, trim: bool) -> None:
        self._wav = WavStream(trim=trim)
        self._wav.feed(_header(rate))
        self.sent = 0

    @property
    def sample_rate(self) -> int:
        return self._wav.sample_rate

    @property
    def speech_s(self) -> float:
        return self._wav.speech_s

    def feed(self, data: bytes) -> AudioChunk | None:
        """The chunk `data` completes, or None while it holds no whole sample (or a trim holds
        the silence back)."""
        pcm = self._wav.feed(data)
        if not pcm:
            return None
        self.sent += 1
        return AudioChunk(pcm16=pcm, sample_rate=self.sample_rate)

    def last(self, text: str, language: str) -> AudioChunk | None:
        """The take's closing chunk once its stream has ended (the module's docstring), or None
        when nothing is left to say about it."""
        tail = self._wav.finish()
        short = cut_short(text, language, self.speech_s)
        if tail or short or not self.sent:
            return AudioChunk(pcm16=tail, sample_rate=self.sample_rate, cut_short=short)
        return None


def too_long(limit: int) -> ProviderError:
    """The refusal of a text over the model's `max_chars`, unsent."""
    return ProviderError("rejected", False, details={"error": "too_long", "max_chars": limit})


def no_voice() -> ProviderError:
    """The refusal of a language the settings give no model or voice, unsent."""
    return ProviderError("rejected", False, details={"error": "no_voice"})
