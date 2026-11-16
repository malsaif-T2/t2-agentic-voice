"""The speech-to-text bridge: Pipecat's STT base class (`STTService`), sending the
`SpeechToText` port one request per user turn (plan 003's decision log; the appendix, "Changes
to the plan's interfaces", items 3 and 4), never one per speech segment as Pipecat's
`SegmentedSTTService` does, and an overlap's two parts besides (plan 005).

It sits after `UserTurnProcessor`, so the turn's frames reach it: it opens a turn on the
downstream `UserStartedSpeakingFrame`, numbering the call's turns from 0, and closes it on the
`UserStoppedSpeakingFrame`, keyed on those frames, never on the processor's events, which run
on tasks of their own (item 6). It holds the turn's audio from a pre-roll before the turn
opened (the turn opens about 0.34 s after its speech began, so the pre-roll is the detector's
start delay plus `PREROLL_PAD_S`) to its close, at most `MAX_TURN_S`, and sends it whole, trimmed
`TRAIL_S` after the speech detector last heard the speech stop, so a turn ended by the 3 s
fallback is not billed its silence. Each request runs on a task of its own, so the next turn's
frames are never held up by it. Each turn reports `TurnOpened`, `TurnClosed` and exactly one
`Transcribed` of its `turn` part, an empty, failed or unusable result included, with its
request's `Transcribing` handed as the request goes (voice/session/io.py's turns and usage). Its
times are the call's clock read as each frame reaches it, never Pipecat's `timestamp` fields:
`speech_at` is when the detector's start reached it less its start delay, and `speech_ended_at`
when its last stop reached it.

A turn the session marks an overlap (`hear_overlap`, its `HearOverlap`) gets two parts, each
from `OVERLAP_LEAD_S` before the detector heard its speech begin: its `window`, once the turn's
held audio covers the command's `window_ms` from there while the speech goes on (none when the
detector hears the speech stop first); and its `overlap`, all of it held, the moment the
detector's stop reaches the bridge, never after the turn analyzer's decision, or at once for a
command that comes after that stop. When no speech follows the overlap part's audio, the turn's
own `Transcribed` is that part's result again, with no request; otherwise the turn's request
goes as for any turn. So at most two requests decide an overlap. Where the parts start and end
is counted in the audio held, never on the clock, which the turn analyzer stalls at each stop.

With `early` (a call with a talker: plan 006's early start), a turn that is no overlap whose
hold began (turn_hold.py's `TurnHeldFrame`) hands `TurnHeld` and sends its speech so far as its
`held` request at once, trimmed as the turn's own would be; speech resumed in the hold
(`HoldResumedFrame`) cancels that request, then hands `HoldResumed`. When no speech followed its
audio, the turn's own `Transcribed` is that request's result again, with no request.

Every request is stt_requests.py's: each names the language `languages` gives it as it goes, with
that language's Whisper prompt (`call_prompts`). The bridge tells `languages` of each turn's
audio, its hold (whatever `early` says), its overlap and its close, and never waits on it.

`drop` ends the call's side here (io.py's end): the held audio is dropped, never flushed, and
every request in flight cancelled, a part's included, its `Transcribing` already handed, and
every classification in flight. A muted service holds no audio (Pipecat's `STTMuteFrame`).
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Mapping

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

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.session_events import (
    HoldResumed,
    Transcribed,
    TurnClosed,
    TurnHeld,
    TurnOpened,
)
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_language import TurnLanguages
from t2_agentic_voice.voice.stt_requests import SttRequests
from t2_agentic_voice.voice.stt_turn import HeldOverlap, HeldTurn
from t2_agentic_voice.voice.turn_hold import HoldResumedFrame, TurnHeldFrame

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
# What an overlap's parts hold before the detector heard its speech begin: the padding before the
# speech that plan 002's window runs held (plan 005's decision log).
OVERLAP_LEAD_S = 0.3


class TurnSTTBridge(STTService):
    """One call's speech-to-text bridge: each user turn's audio to `stt` in one request, and an
    overlap's parts, its events to `events`, its failures to `report`; `start_s` is the speech
    detector's start delay; `early`, a turn's `held` request at its hold; `prompts`, the call's
    Whisper prompt of each language (`call_prompts`; none by default); `languages`, each turn's
    language (no classifier by default) (the module's)."""

    def __init__(
        self,
        *,
        stt: SpeechToText,
        events: EventStream,
        report: FailureReport,
        start_s: float,
        early: bool = False,
        prompts: Mapping[str, str] | None = None,
        languages: TurnLanguages | None = None,
    ) -> None:
        super().__init__(
            audio_passthrough=False,
            settings=STTSettings(model=None, language=None),
            name="t2v-stt-bridge",
        )
        self._events = events
        self._preroll_s = start_s + PREROLL_PAD_S
        self._preroll: deque[bytes] = deque()
        self._preroll_bytes = 0
        self._held = 0  # every byte of audio held so far, the pre-roll's and the turns'
        self._turn: HeldTurn | None = None
        self._last: tuple[int, asyncio.Task[Transcribed]] | None = None  # the last turn closed
        self._next_turn = 0
        self._speech_at: float | None = None
        self._speech_from: int | None = None  # the byte held where the speech last began
        self._stopped_at: float | None = None
        self._languages = languages or TurnLanguages(clock=events.clock)
        self._requests = SttRequests(
            self,
            stt=stt,
            events=events,
            report=report,
            prompts=prompts or {},
            languages=self._languages,
        )
        self._dropped = False
        self._early = early

    @property
    def supports_ttfs(self) -> bool:
        """No streaming time to a final transcript: a turn's one request is timed by its
        events, so Pipecat's turn strategies time none of it."""
        return False

    def listen_in(self, language: str | None) -> None:
        """Name `language` to the provider for every turn's request from now on (`ListenIn`),
        each sent with that language's prompt (the module's)."""
        self._languages.listen_in(language)

    def hear_overlap(self, turn_id: int, window_ms: int) -> None:
        """The turn `turn_id` is an overlap (`HearOverlap`): send its parts, as the module's
        docstring says. A turn closed already gets its own request's result again as its
        `overlap` part, and one the bridge no longer knows an empty part, so every overlap is
        decided."""
        turn = self._turn
        if self._dropped:
            return
        if turn is not None and turn.turn_id == turn_id:
            self._languages.overlap(turn_id)
            if turn.overlap is None:
                overlap = turn.mark(self._bytes(OVERLAP_LEAD_S), self._bytes(window_ms / 1000))
                if turn.cut_at is None:
                    self._window_due(turn)
                else:
                    self._send_overlap(turn, overlap)
        elif self._last is not None and self._last[0] == turn_id:
            self._requests.reuse(self._last[1], "overlap")
        else:
            log.warning("overlap_turn_unknown", turn_id=turn_id)
            self._requests.send(turn_id, b"", "overlap")

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
        self._held += len(frame.audio)
        turn = self._turn
        if turn is None:
            self._preroll.append(frame.audio)
            self._preroll_bytes += len(frame.audio)
            keep = int(self._preroll_s * self.sample_rate) * 2
            while self._preroll_bytes - len(self._preroll[0]) >= keep:
                self._preroll_bytes -= len(self._preroll.popleft())
        elif len(turn.audio) + len(frame.audio) <= int(MAX_TURN_S * self.sample_rate) * 2:
            turn.audio += frame.audio
            self._languages.heard(turn, self.sample_rate)
            self._window_due(turn)
        elif not turn.full:
            turn.full = True
            log.warning("turn_audio_capped", turn_id=turn.turn_id, max_turn_s=MAX_TURN_S)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction != FrameDirection.DOWNSTREAM or self._dropped:
            return
        now, turn = self._events.clock.now(), self._turn
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._speech_at = now - frame.start_secs
            self._speech_from = self._held - self._bytes(frame.start_secs)
            if turn is not None:
                turn.starts += 1
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._stopped_at = now
            if turn is not None:
                turn.stopped()
                if turn.overlap is not None and turn.overlap.part is None:
                    self._send_overlap(turn, turn.overlap)
        elif isinstance(frame, UserStartedSpeakingFrame) and turn is None:
            self._open(now)
        elif isinstance(frame, UserStoppedSpeakingFrame) and turn is not None:
            self._close(turn, now)
        elif isinstance(frame, TurnHeldFrame | HoldResumedFrame) and turn is not None:
            await self._hold(turn, now, began=isinstance(frame, TurnHeldFrame))

    async def _hold(self, turn: HeldTurn, now: float, *, began: bool) -> None:
        """The turn's hold began (its `held` request sent) or resumed (it cancelled), in a call
        with the early start, for a turn that is no overlap (the module's); told to
        `languages` in every call."""
        self._languages.held(turn, self.sample_rate, began=began)
        if not self._early or turn.overlap is not None:
            return
        if began and turn.held is None:
            self._events.hand(TurnHeld(turn_id=turn.turn_id, at=now))
            audio = turn.request(int(TRAIL_S * self.sample_rate) * 2)
            turn.held = self._requests.send(turn.turn_id, audio, "held")
            turn.held_starts = turn.starts
        elif not began and turn.held is not None:
            held, turn.held = turn.held, None
            await self.cancel_task(held)
            self._events.hand(HoldResumed(turn_id=turn.turn_id, at=self._events.clock.now()))

    def _bytes(self, seconds: float) -> int:
        """How many bytes of the caller's audio last `seconds`."""
        return round(seconds * self.sample_rate) * 2

    def _open(self, now: float) -> None:
        audio = bytearray(b"".join(self._preroll))
        start = self._held - len(audio)
        speech = len(audio) if self._speech_from is None else max(0, self._speech_from - start)
        turn = HeldTurn(turn_id=self._next_turn, audio=audio, speech=speech)
        self._next_turn += 1
        self._preroll.clear()
        self._preroll_bytes = 0
        self._turn = turn
        speech_at = now if self._speech_at is None else min(self._speech_at, now)
        self._events.hand(TurnOpened(turn_id=turn.turn_id, at=now, speech_at=speech_at))

    def _close(self, turn: HeldTurn, now: float) -> None:
        self._turn = None
        ended = now if self._stopped_at is None else self._stopped_at
        self._events.hand(TurnClosed(turn_id=turn.turn_id, at=now, speech_ended_at=ended))
        if turn.overlap is not None and turn.overlap.part is None:  # no stop came since marked
            self._send_overlap(turn, turn.overlap)
        self._languages.closed(turn, self.sample_rate)
        reused = turn.reused()
        if reused is not None:
            request = self._requests.reuse(reused, "turn")
        else:
            audio = turn.request(int(TRAIL_S * self.sample_rate) * 2)
            request = self._requests.send(turn.turn_id, audio, "turn")
        self._last = (turn.turn_id, request)

    def _window_due(self, turn: HeldTurn) -> None:
        """The overlap's window, once the audio held covers it, while the speech goes on."""
        window = turn.window()
        if window is not None:
            self._requests.send(turn.turn_id, window, "window")

    def _send_overlap(self, turn: HeldTurn, overlap: HeldOverlap) -> None:
        """The overlap's whole speech, to where the detector last heard it stop."""
        audio = turn.overlap_part(overlap)
        overlap.part = self._requests.send(turn.turn_id, audio, "overlap")

    async def drop(self) -> None:
        """The call has ended: drop the audio held, never sending it, and cancel every request
        in flight."""
        self._dropped = True
        self._turn = self._last = None
        self._preroll.clear()
        await self._requests.drop()
        await self._languages.drop()
