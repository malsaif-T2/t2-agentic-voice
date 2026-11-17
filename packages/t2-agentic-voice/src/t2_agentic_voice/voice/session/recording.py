"""The call's recorder (docs/SECURITY.md, invariant 8): the caller's track, the agent's audio and
the playback timeline of one call, kept under `storage.var_dir` only when `privacy.record_audio`
is on and the caller's consent allows it (`allows_recording`, true only for the consent a
verified signed join token carried). Both are read once, when the call's session is built, from
the settings and the consent the identity source returned at join, so nothing said or sent in
the call (no client message) can turn it on; with either off, nothing is written and no thread
starts.

Under `recordings/<call ID>/` (plan 003's decision log): `caller.wav`, the caller's audio as the
pipeline hears it (the input tap, 16 kHz mono 16-bit), and `agent.wav`, the agent's as the output
transport sends it (the output tap, at the pipeline's output rate), each padded with silence to
where its audio came on the call's clock, so the two line up from the call's start; and
`timeline.jsonl`, one JSON object a line: the call's start, each turn's start and end, the words
heard, each clause asked for (its text), queued, played or failed, what the browser reported
playing, each stop, and the end; each line's `t` is in seconds from the call's start. The files
are written on one thread of the recorder's own, in order, so the call's path never waits on a
disk; a write that fails is logged by its kind alone, and the recording stops there, never
raising into the call's path (as the prototype's recorder did: plan 003's progress log).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import queue
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from pydantic import JsonValue

from t2_agentic_voice.core.identity import allows_recording
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.voice.protocol import Playback, Stop
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    CallerAudio,
    ClauseFailed,
    ClausePlayed,
    ClauseQueued,
    FromClient,
    SessionEvent,
    Transcribed,
    TurnClosed,
    TurnOpened,
)

_log = get_logger(__name__)

# The folder under `storage.var_dir` that holds each recorded call's folder, and its files.
RECORDINGS = "recordings"
CALLER_TRACK = "caller.wav"
AGENT_TRACK = "agent.wav"
TIMELINE = "timeline.jsonl"


@dataclass(frozen=True)
class _Audio:
    """A piece of a track: its file's name, its mono PCM16 at `rate`, and where it starts, in
    seconds from the call's start."""

    track: str
    pcm16: bytes
    rate: int
    offset: float


_Job = _Audio | dict[str, JsonValue]


class _Track:
    """One open WAV track, and how many samples it holds."""

    def __init__(self, path: Path, rate: int) -> None:
        self.rate = rate
        self.samples = 0
        self.file = wave.open(str(path), "wb")  # noqa: SIM115 - closed by `_Files.close`
        self.file.setnchannels(1)
        self.file.setsampwidth(2)
        self.file.setframerate(rate)

    def write(self, piece: _Audio) -> None:
        """Silence up to where `piece` starts, then the piece; a piece at another rate than
        the track's is left out."""
        if piece.rate != self.rate:
            return
        missing = round(piece.offset * self.rate) - self.samples
        if missing > 0:
            self.file.writeframes(b"\x00\x00" * missing)
            self.samples += missing
        self.file.writeframes(piece.pcm16)
        self.samples += len(piece.pcm16) // 2


class _Files:
    """One recorded call's files, each opened when its first line or audio comes."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._tracks: dict[str, _Track] = {}
        self._timeline: IO[str] | None = None

    def take(self, job: _Job) -> bool:
        """Write `job`; False, logged by the failure's kind alone, when a write failed."""
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
            if isinstance(job, _Audio):
                track = self._tracks.get(job.track)
                if track is None:
                    track = self._tracks[job.track] = _Track(self._folder / job.track, job.rate)
                track.write(job)
            else:
                if self._timeline is None:
                    self._timeline = (self._folder / TIMELINE).open("w", encoding="utf-8")
                self._timeline.write(json.dumps(job, ensure_ascii=False) + "\n")
        except (OSError, wave.Error) as error:
            _log.warning("recording_failed", failure=type(error).__qualname__)
            return False
        return True

    def close(self) -> None:
        """Close every file, each WAV header then giving its length."""
        for track in self._tracks.values():
            with contextlib.suppress(OSError, wave.Error):
                track.file.close()
        if self._timeline is not None:
            with contextlib.suppress(OSError):
                self._timeline.close()


class CallRecorder:
    """One call's recorder: `on` only when `privacy.record_audio` is on and the call's consent,
    as the identity source returned it, allows recording (`allows_recording`). Off, every method
    returns at once and writes nothing."""

    def __init__(self, setup: CallSetup) -> None:
        settings = setup.settings
        self.on = settings.privacy.record_audio and allows_recording(setup.consent)
        self._folder = settings.storage.var_dir / RECORDINGS / setup.call_id
        self._consent_version = setup.consent.version
        self._call_id = setup.call_id
        self._jobs: queue.SimpleQueue[_Job | None] = queue.SimpleQueue()
        self._writer: threading.Thread | None = None
        self._start: float | None = None

    def _offset(self, at: float) -> float:
        """Seconds from the call's start, the first time the recorder was given."""
        if self._start is None:
            self._start = at
        return round(at - self._start, 6)

    def _put(self, job: _Job) -> None:
        if self._writer is None:
            self._writer = threading.Thread(
                target=self._work, args=(_Files(self._folder),), name="t2v-recorder", daemon=True
            )
            self._writer.start()
        self._jobs.put(job)

    def _work(self, files: _Files) -> None:
        writing = True
        while (job := self._jobs.get()) is not None:
            writing = writing and files.take(job)
        files.close()

    def line(self, at: float, event: str, **fields: JsonValue) -> None:
        """One line of the timeline: what happened at `at`, on the call's clock."""
        if self.on:
            self._put({"t": self._offset(at), "event": event, **fields})

    def started(self, at: float, wall: str) -> None:
        """The call began at `at` (`wall`, its time of day): the timeline's first line."""
        self.line(at, "start", call_id=self._call_id, wall=wall, consent=self._consent_version)

    def asked(self, at: float, speak: Speak, caption: str) -> None:
        """The session asked for a clause, whose text the caption shows."""
        clause = {"reply_id": speak.reply_id, "clause": speak.clause, "turn_id": speak.turn_id}
        self.line(at, "clause_asked", **clause, cached=speak.audio is not None, text=caption)

    def judged(self, event: Transcribed, verdict: Verdict) -> None:
        """An overlap's transcript, and the interruption rule's verdict on it."""
        text = "" if event.transcript is None else event.transcript.text
        heard = {"turn_id": event.turn_id, "part": event.part, "text": text}
        said = {"action": verdict.action, "kind": verdict.kind, "reason": verdict.reason}
        self.line(event.at, "overlap_judged", **heard, **said)

    def heard(self, at: float, turn_id: int, text: str, *, dropped: bool) -> None:
        """What speech-to-text heard in a turn, and whether the drop rule left it unanswered."""
        self.line(at, "heard", turn_id=turn_id, text=text, dropped=dropped)

    def take(self, event: SessionEvent) -> None:
        """Keep what `event` tells: a tap's audio on its track, anything else the timeline
        keeps as a line."""
        if not self.on:
            return
        match event:
            case CallerAudio() | AgentAudio():
                track = CALLER_TRACK if isinstance(event, CallerAudio) else AGENT_TRACK
                offset = self._offset(event.at)
                self._put(_Audio(track, event.pcm16, event.sample_rate, offset))
            case TurnOpened(turn_id=turn_id, speech_at=speech_at):
                self.line(
                    event.at, "turn_opened", turn_id=turn_id, speech_s=self._offset(speech_at)
                )
            case TurnClosed(turn_id=turn_id, speech_ended_at=ended):
                self.line(
                    event.at, "turn_closed", turn_id=turn_id, speech_ended_s=self._offset(ended)
                )
            case ClauseQueued() | ClausePlayed() | ClauseFailed():
                kind = {ClauseQueued: "queued", ClausePlayed: "played", ClauseFailed: "failed"}
                name = f"clause_{kind[type(event)]}"
                self.line(event.at, name, reply_id=event.reply_id, clause=event.clause)
            case FromClient(message=Playback() as played):
                fields = {"reply_id": played.reply_id, "clause": played.clause}
                self.line(event.at, "playback", **fields, state=played.event)
            case FromClient(message=Stop()):
                self.line(event.at, "stop")

    async def aclose(self) -> None:
        """Finish the recording: every file written and closed, its thread ended; nothing is
        kept after."""
        self.on = False
        if self._writer is not None:
            self._jobs.put(None)
            await asyncio.to_thread(self._writer.join)
            self._writer = None
