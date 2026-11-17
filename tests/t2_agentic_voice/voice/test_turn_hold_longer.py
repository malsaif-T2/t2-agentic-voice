"""A read-back's answer's longer wait (voice/turn_hold.py's `LongerWait`, plan 010's 1.11): the
real turn processor of voice/turns.py, driven by the tone detector and a turn analyzer that needs
no model, its frames timed as they leave it. While the wait is on, a pause Smart Turn judges
unfinished ends the turn at its seconds, the shorter stop timeout (`turns.max_silence_ms`)
waiting for it; speech that starts again drops it; a pause judged complete keeps its hold; and
off, the stop timeout ends the turn, as with no wait at all."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.turn_hold import LongerWait
from t2_agentic_voice.voice.turns import turn_processors

from tests.t2_agentic_voice.voice.kit import (
    PauseAnalyzer,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.processors.frame_processor import FrameDirection

# A stop timeout shorter than the wait, and the hold after a "complete".
TURNS = TurnSettings(complete_hold_ms=300, max_silence_ms=200)
WAIT_S = 0.7
UNFINISHED = 1_000  # every pause of a turn judged unfinished


class _Timed(Tail):
    """A tail that also keeps when, on the loop's clock, each frame reached it."""

    def __init__(self) -> None:
        super().__init__()
        self.at: list[tuple[Frame, float]] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        self.at.append((frame, asyncio.get_running_loop().time()))
        await super().process_frame(frame, direction)

    def when(self, kind: type[object]) -> list[float]:
        return [at for frame, at in self.at if isinstance(frame, kind)]


def _gap(
    longer: LongerWait | None, analyzer: PauseAnalyzer, speech: list[tuple[float, float]]
) -> float:
    """From the detector's last stop to the turn's one end, in seconds, for `speech`'s (tone,
    silence) pairs after 0.2 s of silence."""
    from pipecat.frames.frames import UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame

    vad, user_turns = turn_processors(ToneVAD(), analyzer, TURNS, longer)
    tail = _Timed()

    async def feed(worker: PipelineWorker) -> None:
        frames = list(audio_frames(0.2, loud=False))
        for tone_s, silence_s in speech:
            frames += [*audio_frames(tone_s), *audio_frames(silence_s, loud=False)]
        for frame in frames:
            await worker.queue_frame(frame)
        while not tail.of(UserStoppedSpeakingFrame):
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # no second end follows

    asyncio.run(run_pipeline([vad, user_turns, tail], feed))
    (end,) = tail.when(UserStoppedSpeakingFrame)
    return end - tail.when(VADUserStoppedSpeakingFrame)[-1]


def test_an_unfinished_pause_ends_at_the_wait_while_it_is_on() -> None:
    gap = _gap(LongerWait(seconds=WAIT_S, on=True), PauseAnalyzer(UNFINISHED), [(0.4, 1.2)])
    assert WAIT_S - 0.03 <= gap < WAIT_S + 0.2


@pytest.mark.parametrize("longer", [None, LongerWait(seconds=WAIT_S)], ids=["none", "off"])
def test_off_the_stop_timeout_ends_an_unfinished_pause(longer: LongerWait | None) -> None:
    gap = _gap(longer, PauseAnalyzer(UNFINISHED), [(0.4, 1.2)])
    assert 0.17 <= gap < 0.45


def test_speech_that_starts_again_drops_the_wait_and_the_next_pause_gets_its_own() -> None:
    gap = _gap(
        LongerWait(seconds=WAIT_S, on=True), PauseAnalyzer(UNFINISHED), [(0.4, 0.4), (0.4, 1.2)]
    )
    assert WAIT_S - 0.03 <= gap < WAIT_S + 0.2


def test_a_pause_judged_complete_keeps_its_hold_while_the_wait_is_on() -> None:
    gap = _gap(LongerWait(seconds=WAIT_S, on=True), PauseAnalyzer(), [(0.4, 1.2)])
    assert 0.28 <= gap < 0.55
