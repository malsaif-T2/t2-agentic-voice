"""What the speech-to-text bridge (stt_bridge.py) holds of each turn until its close (`HeldTurn`):
its audio from the pre-roll on, where the speech detector heard its speech begin and last stop,
and, for an overlap, where its parts start and end (`HeldOverlap`). Every place is a byte of the
turn's audio, never a time on the clock, which the turn analyzer stalls at each stop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from t2_agentic_voice.voice.session.session_events import Transcribed


@dataclass
class HeldOverlap:
    """A turn's overlap: where its parts start in the turn's audio (`lead`) and where its window
    ends, whether the window went, and its `overlap` part's request once it went, with the
    detector's starts the turn had heard at that part's last byte (`starts`)."""

    lead: int
    window_end: int
    window_sent: bool = False
    part: asyncio.Task[Transcribed] | None = None
    starts: int = 0


@dataclass
class HeldTurn:
    """One open turn: `turn_id`, its `audio` so far, and `speech`, the byte where the detector
    heard its speech begin; `cut_at`, the bytes held when the detector last heard the speech
    stop, and `cut_starts`, the detector's starts heard by then (`starts`, since the turn
    opened); `full` once `MAX_TURN_S` was reached; its `overlap`, once marked one; and its
    `held` request, sent when its hold began (the early start), with the detector's starts
    heard by then (`held_starts`)."""

    turn_id: int
    audio: bytearray
    speech: int
    cut_at: int | None = None
    starts: int = 0
    cut_starts: int = 0
    full: bool = False
    overlap: HeldOverlap | None = None
    held: asyncio.Task[Transcribed] | None = None
    held_starts: int = 0

    def stopped(self) -> None:
        """The detector heard the speech stop: the turn's audio is cut here."""
        self.cut_at, self.cut_starts = len(self.audio), self.starts

    def voiced_s(self, sample_rate: int) -> float:
        """The seconds of voiced speech held: from where the detector heard the speech begin to
        where it last heard it stop (all held, with no stop yet), never the silence after."""
        end = len(self.audio) if self.cut_at is None else self.cut_at
        return max(0, end - self.speech) / (2 * sample_rate)

    def mark(self, lead: int, window: int) -> HeldOverlap:
        """Mark the turn an overlap whose parts start `lead` bytes before its speech, its window
        `window` bytes long from there."""
        start = self.speech - lead
        self.overlap = HeldOverlap(lead=max(0, start), window_end=start + window)
        return self.overlap

    def window(self) -> bytes | None:
        """The overlap's window, once the audio held covers it while the speech goes on (never
        after the detector heard it stop): marked sent, so it is given once. None otherwise."""
        overlap = self.overlap
        if overlap is None or overlap.window_sent or self.cut_at is not None:
            return None
        if len(self.audio) < overlap.window_end:
            return None
        overlap.window_sent = True
        return bytes(self.audio[overlap.lead : overlap.window_end])

    def overlap_part(self, overlap: HeldOverlap) -> bytes:
        """The overlap's whole speech, to where the detector last heard it stop (all of it held,
        with no stop yet), the turn's audio cut there."""
        if self.cut_at is None:
            self.stopped()
        overlap.starts = self.cut_starts
        return bytes(self.audio[overlap.lead : self.cut_at])

    def reused(self) -> asyncio.Task[Transcribed] | None:
        """The request whose result is the turn's own: its overlap part's, or its `held` one,
        when it went and no speech followed its audio. None when the turn needs a request of
        its own."""
        overlap = self.overlap
        if overlap is not None and overlap.part is not None and overlap.starts == self.starts:
            return overlap.part
        if self.held is not None and self.held_starts == self.starts:
            return self.held
        return None

    def request(self, trail: int) -> bytes:
        """The turn's own request's audio: all of it, trimmed `trail` bytes after the detector's
        last stop."""
        if self.cut_at is None:
            return bytes(self.audio)
        return bytes(self.audio[: self.cut_at + trail])
