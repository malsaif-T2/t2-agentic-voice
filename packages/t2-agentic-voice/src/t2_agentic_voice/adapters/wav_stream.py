"""A WAV file read as it streams in. Groq's Orpheus answers each request with a
WAV whose bytes arrive in chunks split anywhere, even inside a sample, so `WavStream` takes the
bytes as they come and gives back the PCM they hold, always in whole samples.

It reads the format from the `fmt ` chunk: mono 16-bit PCM, at the sample rate the header names,
never assumed (Groq does not state it; 24 kHz per Pipecat's Groq service and the Orpheus code,
UNVERIFIED). It skips the chunks before the audio (the prototype saw a `LIST` chunk there), and
takes every byte after the `data` chunk's header as audio, whatever size that header gives, since
a WAV streamed before its length is known cannot give it. So did the prototype's `WavStream`
(its `voice/tts.py`, lines 43-78, read, never run), which also refused any format but mono
16-bit.

It measures the silence before the speech, in 40 ms frames: the frames before the first whose
loudness passes about -44 dBFS (the prototype's `SILENT_RMS`, its lines 101-107, where Orpheus's
pauses are near-digital silence and its quietest speech far above). With `trim` on it drops that
silence but for its last 40 ms (the prototype's `KEEP_BEFORE`), holding the audio back until the
speech starts; with `trim` off (`tts.trim_silence`'s default) the audio passes as it comes. Only
the silence before the speech is trimmed: the pauses inside it and the silence after it are
kept, which the prototype also cut (plan 003's decision log: runs T1 and T2 measure the leading
silence before the latency target weighs it).
"""

from __future__ import annotations

import math
import struct

# A frame of the silence measure, in seconds, and how loud a frame is, as a share of full scale
# (its RMS), before it counts as speech: about -44 dBFS (the prototype's).
FRAME_S = 0.04
SILENT_RMS = 0.006
_FULL_SCALE = 32768
# RIFF's head ("RIFF", the size, "WAVE") and each chunk's head (its four-letter kind, its size).
_RIFF_HEAD = 12
_CHUNK_HEAD = 8
# The `fmt ` chunk's format tags that hold integer PCM: plain, and the extensible form.
_PCM_TAGS = (0x0001, 0xFFFE)
_FMT_BYTES = 16


class WavError(ValueError):
    """A stream that is not a mono 16-bit PCM WAV, or that ended before its audio began. Its
    message is fixed text, never the stream's bytes."""


class WavStream:
    """One WAV, read as it streams in: `feed` each piece as it arrives, then `finish` once the
    stream has ended. `trim` drops the silence before the speech (above)."""

    def __init__(self, *, trim: bool = False) -> None:
        self.trim = trim
        self._rate: int | None = None
        self._head = bytearray()  # the header, until the audio starts
        self._in_audio = False
        self._odd = b""  # half a sample, carried to the next piece
        self._samples = 0  # samples received, before any trim
        self._frame_bytes = 0
        self._silent_frames = 0  # the whole frames scanned before the speech, all silent
        self._speech_frame: int | None = None  # the first loud frame's index
        self._unscanned = bytearray()  # audio not yet scanned for the speech
        self._before = b""  # the last silent frame scanned, kept before the speech when trimming

    @property
    def sample_rate(self) -> int:
        """The sample rate the header names. WavError before the header has given it."""
        if self._rate is None:
            raise WavError("the WAV stream has not given its format yet")
        return self._rate

    @property
    def audio_s(self) -> float:
        """How long the audio received so far plays, before any trim."""
        return self._samples / self._rate if self._rate else 0.0

    @property
    def leading_silence_s(self) -> float | None:
        """The silence before the speech, to the 40 ms frame; None while no speech was found
        (a take of silence alone has none)."""
        if self._speech_frame is None or self._rate is None:
            return None
        return self._speech_frame * (self._frame_bytes // 2) / self._rate

    @property
    def speech_s(self) -> float:
        """How long the audio plays from its speech's start to its end; 0 with no speech."""
        silence = self.leading_silence_s
        return 0.0 if silence is None else max(0.0, self.audio_s - silence)

    def feed(self, data: bytes) -> bytes:
        """The audio `data` completes, in whole samples (empty while the header is still coming,
        or while a trim holds the silence back). WavError for a stream that is not a mono
        16-bit PCM WAV."""
        if not self._in_audio:
            self._head += data
            data = self._past_header()
            if not self._in_audio:
                return b""
        data = self._odd + data
        whole = len(data) - len(data) % 2
        self._odd = data[whole:]
        return self._audio(data[:whole])

    def finish(self) -> bytes:
        """The audio still held once the stream has ended: with `trim` on and no speech found
        yet, the silence held back when its last piece of a frame is loud, else nothing. Half a
        sample left over is dropped. WavError when the stream ended before its audio began."""
        if not self._in_audio:
            raise WavError("the WAV stream ended before its audio")
        self._odd = b""
        rest = bytes(self._unscanned)
        self._unscanned.clear()
        if self._speech_frame is None and rest and _loud(rest):
            self._speech_frame = self._silent_frames
            return self._before + rest if self.trim else b""
        return b""

    def _past_header(self) -> bytes:
        """The bytes after the `data` chunk's head once the header holds it (the stream is then
        in its audio), else nothing yet."""
        head = self._head
        if len(head) < _RIFF_HEAD:
            return b""
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise WavError("the answer is not a WAV stream")
        at = _RIFF_HEAD
        while len(head) >= at + _CHUNK_HEAD:
            kind = bytes(head[at : at + 4])
            size = int.from_bytes(head[at + 4 : at + _CHUNK_HEAD], "little")
            body = at + _CHUNK_HEAD
            if kind == b"data":
                if self._rate is None:
                    raise WavError("the WAV stream's audio came before its format")
                self._in_audio = True
                rest = bytes(head[body:])
                self._head = bytearray()
                return rest
            if len(head) < body + size:
                return b""
            if kind == b"fmt ":
                self._format(bytes(head[body : body + size]))
            at = body + size + size % 2  # a chunk of odd size is padded to an even one
        return b""

    def _format(self, fmt: bytes) -> None:
        """Read the `fmt ` chunk: mono 16-bit integer PCM, at its own sample rate."""
        if len(fmt) < _FMT_BYTES:
            raise WavError("the WAV stream's format is cut short")
        tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:_FMT_BYTES])
        if tag not in _PCM_TAGS or (channels, bits) != (1, 16) or rate <= 0:
            raise WavError("the WAV stream is not mono 16-bit PCM")
        self._rate = rate
        self._frame_bytes = max(1, round(rate * FRAME_S)) * 2

    def _audio(self, pcm: bytes) -> bytes:
        """`pcm` as it plays: as it comes once the speech has started, or with `trim` off;
        before it, with `trim` on, nothing until a loud frame comes, then the last silent frame
        and all from the loud one on."""
        self._samples += len(pcm) // 2
        if self._speech_frame is not None:
            return pcm
        self._unscanned += pcm
        held = b""
        while len(self._unscanned) >= self._frame_bytes:
            frame = bytes(self._unscanned[: self._frame_bytes])
            if _loud(frame):
                self._speech_frame = self._silent_frames
                held = self._before + bytes(self._unscanned)
                self._unscanned.clear()
                break
            del self._unscanned[: self._frame_bytes]
            self._silent_frames += 1
            self._before = frame
        return held if self.trim else pcm


def _loud(pcm: bytes) -> bool:
    """Whether `pcm` (whole samples, at least one) is louder than the silence measure's floor."""
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return rms / _FULL_SCALE > SILENT_RMS
