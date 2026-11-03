"""The speech-to-text bridge: Pipecat's STT base class (`STTService`), sending the
`SpeechToText` port one request per user turn (plan 003's decision log; the appendix, "Changes
to the plan's interfaces", items 3 and 4), never one per speech segment as Pipecat's
`SegmentedSTTService` does.

It sits after `UserTurnProcessor`, so the turn's frames reach it: it opens a turn on the
downstream `UserStartedSpeakingFrame`, numbering the call's turns from 0, and closes it on the
`UserStoppedSpeakingFrame`, keyed on those frames, never on the processor's events, which run
on tasks of their own (item 6). It holds the turn's audio from a pre-roll before the turn
opened (the turn opens about 0.34 s after its speech began, so the pre-roll is the detector's
start delay plus `PREROLL_PAD_S`) to its close, at most `MAX_TURN_S`, and sends it whole, trimmed
`TRAIL_S` after the speech detector last heard the speech stop, so a turn ended by the 3 s
fallback is not billed its silence. The request runs on a task of its own, so the next turn's
frames never wait on it. Each turn reports `TurnOpened`, `TurnClosed` and exactly one
`Transcribed`, an empty, failed or unusable result included, with its request's `Transcribing`
handed as the request goes (voice/session/io.py's turns and usage). Its times are the call's
clock read as each frame reaches it, never Pipecat's `timestamp` fields: `speech_at` is when the
detector's start reached it less its start delay, and `speech_ended_at` when its last stop
reached it.

`drop` ends the call's side here (io.py's end): the held audio is dropped, never flushed, and
any request in flight cancelled, its `Transcribing` already handed. A muted service holds no
audio (Pipecat's `STTMuteFrame`).
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import STTService

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import CallEvents

log = get_logger(__name__)

# The audio held before a turn opens, beyond the detector's start delay: the turn opens about
# 0.34 s after its speech began with a 200 ms start delay (plan 003's spike), so the start
# delay and half a second keep the speech's onset with a margin (the agent's value).
PREROLL_PAD_S = 0.5
# The audio a request keeps after the speech detector's last stop in the turn: with its 200 ms
# stop delay, about the half second of silence Pipecat's own segmented bridge pads a segment
# with (`trailing_silence_secs`), the rest of a fallback turn's silence left unbilled (the
# agent's value).
TRAIL_S = 0.3
# The most audio one turn's request holds; Pipecat caps none (item 4). Half a minute is far
# past any request of the golden set; a longer turn keeps its first half minute (the agent's
# value).
MAX_TURN_S = 30.0


@dataclass
class _Turn:
    turn_id: int
    audio: bytearray
    cut_at: int | None = None  # the bytes held when the detector last heard the speech stop
    full: bool = False  # MAX_TURN_S reached: later audio is not kept


class TurnSTTBridge(STTService):
    """One call's speech-to-text bridge: each user turn's audio to `stt` in one request, its
    events to `events`, its failures to `report`; `start_s` is the speech detector's start
    delay."""

    def __init__(
        self, *, stt: SpeechToText, events: CallEvents, report: FailureReport, start_s: float
    ) -> None:
        super().__init__(
            audio_passthrough=False,
            settings=STTSettings(model=None, language=None),
            name="t2v-stt-bridge",
        )
        self._stt = stt
        self._events = events
        self._report = report
        self._preroll_s = start_s + PREROLL_PAD_S
        self._preroll: deque[bytes] = deque()
        self._preroll_bytes = 0
        self._turn: _Turn | None = None
        self._next_turn = 0
        self._speech_at: float | None = None
        self._stopped_at: float | None = None
        self._language: str | None = None
        self._requests: set[asyncio.Task[None]] = set()
        self._dropped = False

    @property
    def supports_ttfs(self) -> bool:
        """No streaming time to a final transcript: a turn's one request is timed by its
        events, so Pipecat's turn strategies wait on none of it."""
        return False

    def listen_in(self, language: str | None) -> None:
        """Name `language` to the provider for every turn's request from now on (`ListenIn`)."""
        self._language = language

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        """Nothing: the base calls this only from `process_audio_frame`, which the bridge
        replaces, since a frame's audio is never a request of its own (a turn's is)."""
        yield None

    async def process_audio_frame(
        self, frame: InputAudioRawFrame, direction: FrameDirection
    ) -> None:
        """Hold the frame's audio: in the open turn, or in the pre-roll before one opens."""
        if self._muted or self._dropped or not frame.audio:
            return
        turn = self._turn
        if turn is None:
            self._preroll.append(frame.audio)
            self._preroll_bytes += len(frame.audio)
            keep = int(self._preroll_s * self.sample_rate) * 2
            while self._preroll_bytes - len(self._preroll[0]) >= keep:
                self._preroll_bytes -= len(self._preroll.popleft())
        elif len(turn.audio) + len(frame.audio) <= int(MAX_TURN_S * self.sample_rate) * 2:
            turn.audio += frame.audio
        elif not turn.full:
            turn.full = True
            log.warning("turn_audio_capped", turn_id=turn.turn_id, max_turn_s=MAX_TURN_S)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction != FrameDirection.DOWNSTREAM or self._dropped:
            return
        now = self._events.clock.now()
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._speech_at = now - frame.start_secs
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._stopped_at = now
            if self._turn is not None:
                self._turn.cut_at = len(self._turn.audio)
        elif isinstance(frame, UserStartedSpeakingFrame) and self._turn is None:
            self._open(now)
        elif isinstance(frame, UserStoppedSpeakingFrame) and self._turn is not None:
            self._close(self._turn, now)

    def _open(self, now: float) -> None:
        turn = _Turn(turn_id=self._next_turn, audio=bytearray(b"".join(self._preroll)))
        self._next_turn += 1
        self._preroll.clear()
        self._preroll_bytes = 0
        self._turn = turn
        speech_at = now if self._speech_at is None else min(self._speech_at, now)
        self._events.hand(TurnOpened(turn_id=turn.turn_id, at=now, speech_at=speech_at))

    def _close(self, turn: _Turn, now: float) -> None:
        self._turn = None
        ended = now if self._stopped_at is None else self._stopped_at
        self._events.hand(TurnClosed(turn_id=turn.turn_id, at=now, speech_ended_at=ended))
        audio = bytes(turn.audio)
        if turn.cut_at is not None:
            audio = audio[: turn.cut_at + int(TRAIL_S * self.sample_rate) * 2]
        request = self.create_task(self._transcribe(turn.turn_id, audio), name="t2v-stt-request")
        self._requests.add(request)
        request.add_done_callback(self._requests.discard)

    async def _transcribe(self, turn_id: int, audio: bytes) -> None:
        events, clock = self._events, self._events.clock
        if not audio or not self.is_usable:
            done = Transcribed(
                turn_id=turn_id, at=clock.now(), audio_s=0.0, sent_at=None, transcript=None
            )
            events.hand(done)
            return
        clip = AudioClip(pcm16=audio, sample_rate=self.sample_rate)
        sent_at = clock.now()
        events.hand(Transcribing(turn_id=turn_id, at=sent_at, audio_s=clip.seconds))
        try:
            transcript = await self._stt.transcribe(clip, language=self._language, prompt=None)
        except ProviderError as error:
            failure, retryable = error.kind, error.retryable
        except Exception as error:  # an adapter's bug: still exactly one result for the turn
            log.error("stt_request_failed", turn_id=turn_id, error=type(error).__name__)
            failure, retryable = "server_error", False
        else:
            events.hand(
                Transcribed(
                    turn_id=turn_id,
                    at=clock.now(),
                    audio_s=clip.seconds,
                    sent_at=sent_at,
                    transcript=transcript,
                )
            )
            return
        self._report.provider_failed("speech_to_text", failure, retryable, turn_id=turn_id)
        events.hand(
            Transcribed(
                turn_id=turn_id,
                at=clock.now(),
                audio_s=clip.seconds,
                sent_at=sent_at,
                transcript=None,
                failure=failure,
                retryable=retryable,
            )
        )

    async def drop(self) -> None:
        """The call has ended: drop the audio held, never sending it, and cancel every request
        in flight."""
        self._dropped = True
        self._turn = None
        self._preroll.clear()
        for request in list(self._requests):
            await self.cancel_task(request)
