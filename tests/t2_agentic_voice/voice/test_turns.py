"""A call's turn detection (voice/turns.py): Silero and Smart Turn from the settings, and the
turn processors with Pipecat's interruptions off."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.turns import speech_detector, turn_analyzer, turn_processors, vad_params

from tests.t2_agentic_voice.voice.kit import (
    PauseAnalyzer,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.pipeline.worker import PipelineWorker


def test_the_speech_detectors_parameters_are_the_settings() -> None:
    turns = TurnSettings(vad_confidence=0.5, vad_start_ms=300, vad_stop_ms=250, vad_min_volume=0.1)
    params = vad_params(turns)
    assert (params.confidence, params.start_secs, params.stop_secs, params.min_volume) == (
        0.5,
        0.3,
        0.25,
        0.1,
    )


@pytest.mark.parametrize("smart_turn", [True, False])
def test_a_turn_starts_and_ends_with_no_pipecat_interruption(smart_turn: bool) -> None:
    """Pipecat's interruptions are off (plan 003's appendix, item 2): a turn's start pushes
    `UserStartedSpeakingFrame` and no `InterruptionFrame`, either way, and a pause ends the
    turn, the analyzer's decision or, with Smart Turn off, the pause alone."""
    from pipecat.frames.frames import (
        InterruptionFrame,
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
    )

    analyzer = PauseAnalyzer() if smart_turn else None
    vad, user_turns = turn_processors(ToneVAD(), analyzer, TurnSettings())
    tail = Tail()

    async def feed(worker: PipelineWorker) -> None:
        for frame in [*audio_frames(0.2, loud=False), *audio_frames(0.4)]:
            await worker.queue_frame(frame)
        for frame in audio_frames(1.0, loud=False):
            await worker.queue_frame(frame)
            await asyncio.sleep(0.005)
        await until(lambda: bool(tail.of(UserStoppedSpeakingFrame)))

    asyncio.run(run_pipeline([vad, user_turns, tail], feed))
    assert len(tail.of(UserStartedSpeakingFrame)) == 1
    assert not [f for f, _ in tail.frames if isinstance(f, InterruptionFrame)]


def test_silero_and_smart_turn_load_on_the_cpu_with_no_torch() -> None:
    """Each model is built from the settings, its ONNX model loaded when built, and nothing
    imports torch (the design's 13)."""
    turns = TurnSettings(smart_turn_stop_ms=2500, smart_turn_pre_speech_ms=400)
    detector, analyzer = speech_detector(turns), turn_analyzer(turns)
    assert type(detector).__name__ == "SileroVADAnalyzer" and detector.params.stop_secs == 0.2
    assert type(analyzer).__name__ == "LocalSmartTurnAnalyzerV3"
    assert analyzer.params.model_dump()["stop_secs"] == 2.5
    assert "onnxruntime" in sys.modules and "torch" not in sys.modules
