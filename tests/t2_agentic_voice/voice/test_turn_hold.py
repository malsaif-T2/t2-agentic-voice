"""The hold after Smart Turn's "complete" (voice/turn_hold.py, `turns.complete_hold_ms`): the
real turn processor of voice/turns.py, driven by the tone detector and a turn analyzer that needs
no model, its frames timed as they leave it. A verdict at a pause ends the turn only after the
hold; speech within it cancels the end; the detector's stop is never held, nor the silence
fallback, nor a call without Smart Turn; at 0 the strategy is Pipecat's own."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.turn_hold import HeldTurnStop
from t2_agentic_voice.voice.turns import turn_processors

from tests.t2_agentic_voice.voice.kit import (
    PauseAnalyzer,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer, EndOfTurnState
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class _Timed(Tail):
    """A tail that also keeps when, on the loop's clock, each frame reached it."""

    def __init__(self) -> None:
        super().__init__()
        self.at: list[tuple[Frame, float]] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        self.at.append((frame, asyncio.get_running_loop().time()))
        await super().process_frame(frame, direction)

    def when(self, kind: type[object]) -> list[float]:
        """When each frame of `kind` reached it, in order."""
        return [at for frame, at in self.at if isinstance(frame, kind)]


class _Fallback(PauseAnalyzer):
    """A turn analyzer that calls every pause unfinished and ends the turn itself once
    `silence_frames` silent frames have followed speech, as Smart Turn's silence fallback."""

    def __init__(self, silence_frames: int) -> None:
        super().__init__(incomplete=1_000)
        self.silence_frames = silence_frames
        self._spoke, self._silent = False, 0

    def append_audio(self, buffer: bytes, is_speech: bool) -> EndOfTurnState:
        from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState

        self._spoke = self._spoke or is_speech
        self._silent = 0 if is_speech else self._silent + self._spoke
        if self._spoke and self._silent >= self.silence_frames:
            self._spoke, self._silent = False, 0
            return EndOfTurnState.COMPLETE
        return EndOfTurnState.INCOMPLETE


def _strategy(user_turns: FrameProcessor) -> object:
    """The stop strategy of a `UserTurnProcessor` (its controller's, which Pipecat keeps)."""
    controller = user_turns._user_turn_controller  # type: ignore[attr-defined]
    return controller.user_turn_strategies.stop[0]


async def _speak(worker: PipelineWorker, tone_s: float, silence_s: float) -> None:
    """`tone_s` of the fakes' tone, then `silence_s` of silence, both at once."""
    for frame in [*audio_frames(tone_s), *audio_frames(silence_s, loud=False)]:
        await worker.queue_frame(frame)


def _run(
    turns: TurnSettings,
    analyzer: BaseTurnAnalyzer | None,
    speech: list[tuple[float, float]],
    *,
    until_stopped: bool = True,
) -> tuple[_Timed, object]:
    """The turn processors of `turns` around `analyzer`, fed `speech`'s (tone, silence) pairs
    after 0.2 s of silence; then, with `until_stopped`, until the turn has ended, else until the
    detector has stopped once more than it had."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame

    vad, user_turns = turn_processors(ToneVAD(), analyzer, turns)
    tail = _Timed()

    async def feed(worker: PipelineWorker) -> None:
        for frame in audio_frames(0.2, loud=False):
            await worker.queue_frame(frame)
        for tone_s, silence_s in speech:
            await _speak(worker, tone_s, silence_s)
        if until_stopped:
            await until(lambda: bool(tail.of(UserStoppedSpeakingFrame)))
            await asyncio.sleep(0.05)  # no second end follows
        else:
            await until(lambda: len(tail.of(VADUserStoppedSpeakingFrame)) == len(speech))

    asyncio.run(run_pipeline([vad, user_turns, tail], feed))
    return tail, _strategy(user_turns)


def _gap(tail: _Timed) -> float:
    """From the detector's last stop to the turn's end, in seconds, as they left the processor."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame

    (end,) = tail.when(UserStoppedSpeakingFrame)
    return end - tail.when(VADUserStoppedSpeakingFrame)[-1]


@pytest.mark.parametrize("hold_ms", [0, 300])
def test_a_turn_judged_complete_ends_after_the_hold_and_at_0_as_pipecats_own(hold_ms: int) -> None:
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

    tail, strategy = _run(TurnSettings(complete_hold_ms=hold_ms), PauseAnalyzer(), [(0.4, 0.3)])
    gap = _gap(tail)
    assert hold_ms / 1000 - 0.02 <= gap < hold_ms / 1000 + 0.25
    held = type(strategy) is HeldTurnStop
    assert held == (hold_ms > 0)
    assert held or type(strategy) is TurnAnalyzerUserTurnStopStrategy
    assert not getattr(strategy, "decision_scheduled", False)


def test_speech_that_resumes_within_the_hold_cancels_the_end_and_the_turn_goes_on() -> None:
    """The first pause is judged complete and held; the tone starts again within the hold, so
    the turn goes on, and the second pause, judged again, ends it after its own hold."""
    from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )

    analyzer = PauseAnalyzer()
    turns = TurnSettings(complete_hold_ms=1000)
    tail, _ = _run(turns, analyzer, [(0.4, 0.3), (0.4, 0.3)])
    assert analyzer.decided == [EndOfTurnState.COMPLETE, EndOfTurnState.COMPLETE]
    counts = [len(tail.of(kind)) for kind in (UserStartedSpeakingFrame, UserStoppedSpeakingFrame)]
    assert (counts, len(tail.of(VADUserStoppedSpeakingFrame))) == ([1, 1], 2)
    assert 0.98 <= _gap(tail) < 1.25


def test_the_detectors_stop_leaves_at_once_while_the_end_is_held() -> None:
    """The stop an overlap's decision waits on (voice/stt_bridge.py) is never delayed: it has
    left the processor while the end is still held."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame

    tail, strategy = _run(
        TurnSettings(complete_hold_ms=1000), PauseAnalyzer(), [(0.4, 0.3)], until_stopped=False
    )
    assert len(tail.of(VADUserStoppedSpeakingFrame)) == 1
    assert not tail.of(UserStoppedSpeakingFrame)  # the call ended within the hold
    assert not getattr(strategy, "decision_scheduled", True)  # its hold dropped at the end


def test_the_silence_fallback_and_a_call_without_smart_turn_end_the_turn_at_once() -> None:
    """Only the model's verdict at a pause is held: the analyzer's own silence fallback, and
    every pause when Smart Turn is off, end the turn with no hold."""
    turns = TurnSettings(complete_hold_ms=1000)
    fallback, _ = _run(turns, _Fallback(silence_frames=15), [(0.4, 0.5)])
    assert _gap(fallback) < 0.5
    off, strategy = _run(turns, None, [(0.4, 0.3)])
    assert _gap(off) < 0.5 and type(strategy).__name__ == "SpeechTimeoutUserTurnStopStrategy"


def test_the_stop_timeout_waits_for_a_held_end() -> None:
    """A stop timeout shorter than the hold (`turns.max_silence_ms`) waits for it: the turn ends
    once, when the hold has passed."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame

    turns = TurnSettings(complete_hold_ms=600, max_silence_ms=100)
    tail, _ = _run(turns, PauseAnalyzer(), [(0.4, 0.3)])
    assert len(tail.of(UserStoppedSpeakingFrame)) == 1
    assert 0.58 <= _gap(tail) < 0.85
