"""What the text-to-speech bridge (tts_bridge.py) keeps of each take as it plays: its audio in the
output transport's whole chunks (`OutputChunks`), and what came of each clause so far, until its
`ClausePlayed` (`ClauseTake`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipecat.audio.utils import create_stream_resampler

from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.transport import OUT_CHUNK_10MS


class OutputChunks:
    """One take's audio as the output transport plays it: at `sample_rate`, mono PCM16, in
    whole chunks of `OUT_CHUNK_10MS` (the size Pipecat's output cuts, 1920 bytes at 24 kHz)."""

    def __init__(self, sample_rate: int) -> None:
        self._rate = sample_rate
        self._size = sample_rate // 100 * 2 * OUT_CHUNK_10MS
        self._held = bytearray()
        # The take's own, its history kept however long the provider pauses.
        self._resampler = create_stream_resampler(clear_after_secs=None)

    async def whole(self, chunk: AudioChunk) -> bytes:
        """The whole chunks the take's audio fills so far, the provider's `chunk` included;
        what falls short of one is held for the next."""
        audio = chunk.pcm16
        if chunk.sample_rate != self._rate:
            audio = await self._resampler.resample(audio, chunk.sample_rate, self._rate)
        self._held.extend(audio)
        cut = len(self._held) - len(self._held) % self._size
        whole = bytes(self._held[:cut])
        del self._held[:cut]
        return whole

    async def rest(self) -> bytes:
        """The take's end: what is held, the resampler's tail with it, padded with silence to
        a whole chunk; nothing when nothing is held."""
        self._held.extend(await self._resampler.flush())
        rest = bytes(self._held) + bytes(-len(self._held) % self._size)
        self._held.clear()
        return rest


@dataclass
class ClauseTake:
    """What came of one clause so far, until its `ClausePlayed`."""

    turn_id: int | None
    requested_at: float | None = None
    queued: bool = False
    audio_s: float = 0.0
    chunks: int = 0
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    cut_short: bool = False
    failed: bool = False
    answered: bool = False

    def took(self, chunk: AudioChunk) -> None:
        """Count a chunk: the headroom on the response's first, the audio of each that holds
        some, and a take cut short on any (the port flags its last)."""
        if not self.answered:
            self.answered = True
            self.remaining_requests = chunk.remaining_requests
            self.remaining_tokens = chunk.remaining_tokens
        if chunk.pcm16:
            self.chunks += 1
            self.audio_s += chunk.seconds
        self.cut_short = self.cut_short or chunk.cut_short
