"""The hold after Smart Turn's "complete" (`turns.complete_hold_ms`, plan 005's amendment (8)):
when the turn analyzer judges a pause the end of the turn, the turn ends only once the hold has
passed with no speech, and speech that resumes within it, as the speech detector hears it start,
cancels the end, the turn going on, Smart Turn judging again at the next pause. It bridges the
caller's pauses inside a request, which Smart Turn v3.2 scores as complete as it scores the true
ends (E1, plan 005's progress log), at the cost of the hold on every turn's end.

`HeldTurnStop` is Pipecat 1.15.0's `TurnAnalyzerUserTurnStopStrategy` with that hold, built by
voice/turns.py only when the hold is above 0, so at 0 a turn's end is Pipecat's own. It acts on
the turn's end alone: the speech detector's `VADUserStoppedSpeakingFrame`, which an overlap's
decision waits on (voice/stt_bridge.py), leaves the `VADProcessor` before the turn processor and
is never delayed. Only the model's verdict is held, the one the strategy reports while it
handles that frame; the analyzer's silence fallback (`turns.smart_turn_stop_ms`), reported as it
handles the caller's audio, ends the turn at once, since a silence that long already bridges any
pause.

What it rests on: it overrides only public members (`process_frame`, `report_user_turn_stopped`,
`decision_scheduled`, `handle_user_turn_stopped` and `cleanup`), but it relies on how 1.15.0's
strategy calls them, which is private: with `wait_for_transcript=False`, its
`_maybe_report_user_turn_stopped` (`turn_analyzer_user_turn_stop_strategy.py`, lines 322-341)
reports the verdict from within `_handle_vad_user_stopped_speaking` (line 269), and the silence
fallback from `_handle_input_audio` (line 210). The controller's stop timeout
(`turns.max_silence_ms`) waits while a hold is scheduled (`decision_scheduled`). Smart Turn keeps
the turn's audio through the hold (smart_turn.py's `keep_turn`), so its next judgement hears the
whole turn, not only the speech after the pause. An upgrade of Pipecat must check those paths
(the tests drive the real strategy through the turn processor).

The early start (plan 006, Q2) adds two signals, each pushed downstream from the turn processor
as a frame of its own, behind the detector's frame that caused it: the hold began (`hold_began`,
a `TurnHeldFrame`), so the speech-to-text bridge sends the turn's speech so far at once and the
session starts the talker on it, playing nothing before the hold ends; and the caller resumed
within it (`hold_resumed`, a `HoldResumedFrame`, given only when speech dropped a hold), so that
work is cancelled and what follows joins the turn. The bridge hands each to the session as its
event (session_events.py's `TurnHeld` and `HoldResumed`), in a call with a talker only
(stt_bridge.py's `early`). A hold the turn's end dropped otherwise (the stop timeout) or the
cleanup signals nothing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import (
    Frame,
    SystemFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy


@dataclass
class TurnHeldFrame(SystemFrame):
    """Smart Turn called the open turn complete, and its hold began."""


@dataclass
class HoldResumedFrame(SystemFrame):
    """The caller spoke again within the open turn's hold, which was dropped."""


# Pipecat 1.15.0 leaves the base's `__init_subclass__`, `handle_user_turn_stopped` and `cleanup`
# unannotated, so subclassing it and calling them are untyped calls to mypy (the ignores below).
class HeldTurnStop(TurnAnalyzerUserTurnStopStrategy):  # type: ignore[no-untyped-call]
    """Pipecat's stop strategy on a turn analyzer, its verdict that a pause ends the turn held
    `hold_s` seconds (above 0) and dropped when the caller speaks again within them; the other
    arguments are Pipecat's."""

    def __init__(self, *, hold_s: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.hold_s = hold_s
        self._at_stop = False  # handling the detector's stop, where the verdict is reported
        self._hold: asyncio.Task[None] | None = None

    @property
    def decision_scheduled(self) -> bool:
        """Whether a held end is due, which the controller's stop timeout waits for."""
        return self._hold is not None

    async def process_frame(self, frame: Frame) -> None:
        """Pipecat's handling of `frame`; speech that starts again drops a held end first."""
        if isinstance(frame, VADUserStartedSpeakingFrame) and self._hold is not None:
            await self._drop_hold()
            await self.hold_resumed()
        self._at_stop = isinstance(frame, VADUserStoppedSpeakingFrame)
        try:
            await super().process_frame(frame)
        finally:
            self._at_stop = False

    async def report_user_turn_stopped(
        self, *, enable_user_speaking_frames: bool | None = None, confirms_speculation: bool = False
    ) -> None:
        """The turn's end: held when it is the analyzer's verdict at a pause, else at once."""
        if not self._at_stop:
            await super().report_user_turn_stopped(
                enable_user_speaking_frames=enable_user_speaking_frames,
                confirms_speculation=confirms_speculation,
            )
        elif self._hold is None:
            self._hold = self.task_manager.create_task(
                self._end_after_hold(enable_user_speaking_frames, confirms_speculation),
                f"{self}::complete_hold",
            )
            await self.hold_began()

    async def hold_began(self) -> None:
        """Smart Turn called the turn complete and the hold began: signal it downstream (a
        `TurnHeldFrame`), so the session starts the turn's transcription and the talker early
        (the module's docstring)."""
        await self.push_frame(TurnHeldFrame())

    async def hold_resumed(self) -> None:
        """The caller spoke again within the hold, which is dropped: signal it downstream (a
        `HoldResumedFrame`), so the early work is cancelled and the turn goes on (the module's
        docstring)."""
        await self.push_frame(HoldResumedFrame())

    async def handle_user_turn_stopped(self) -> None:
        """A turn ended otherwise (the stop timeout, say) holds no end of its own any more."""
        await self._drop_hold()
        await super().handle_user_turn_stopped()  # type: ignore[no-untyped-call]

    async def cleanup(self) -> None:
        """Pipecat's cleanup, a held end dropped first."""
        await self._drop_hold()
        await super().cleanup()  # type: ignore[no-untyped-call]

    async def _end_after_hold(
        self, enable_user_speaking_frames: bool | None, confirms_speculation: bool
    ) -> None:
        await asyncio.sleep(self.hold_s)
        self._hold = None  # before the report, whose turn end comes back to `_drop_hold`
        await super().report_user_turn_stopped(
            enable_user_speaking_frames=enable_user_speaking_frames,
            confirms_speculation=confirms_speculation,
        )

    async def _drop_hold(self) -> None:
        hold, self._hold = self._hold, None
        if hold is not None:
            await self.task_manager.cancel_task(hold)
