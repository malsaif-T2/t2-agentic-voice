"""A call's turn detection (voice/turns.py): Silero and Smart Turn from the settings, and the
turn processors with Pipecat's interruptions off."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import pytest
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.turns import speech_detector, turn_analyzer, turn_processors, vad_params

from tests.t2_agentic_voice.fakes import tone
from tests.t2_agentic_voice.voice.kit import (
    PauseAnalyzer,
    Tail,
    ToneVAD,
    audio_frames,
    run_pipeline,
    until,
)

if TYPE_CHECKING:
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
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
    assert type(analyzer).__name__ == "ThresholdSmartTurn"
    assert type(analyzer).__mro__[1].__name__ == "LocalSmartTurnAnalyzerV3"
    assert analyzer.params.model_dump()["stop_secs"] == 2.5
    assert "onnxruntime" in sys.modules and "torch" not in sys.modules
    for threads in (1, 2):  # `turns.smart_turn_threads`, one by default as Pipecat's own
        made = turn_analyzer(TurnSettings(smart_turn_threads=threads))
        options = made._session.get_session_options()  # type: ignore[attr-defined]
        assert options.intra_op_num_threads == threads
    assert TurnSettings().smart_turn_threads == 1


class _Said:
    """One of the model's outputs, as its ONNX session gives it (`item()`)."""

    def __init__(self, probability: float) -> None:
        self.probability = probability

    def item(self) -> float:
        return self.probability


class _Model:
    """In place of Smart Turn's ONNX session: the model is `probability` sure, whatever it
    hears."""

    def __init__(self, probability: float) -> None:
        self.probability = probability

    def run(self, names: object, inputs: object) -> list[list[_Said]]:
        return [[_Said(self.probability)]]


async def _decide(analyzer: BaseTurnAnalyzer, model: _Model | None = None) -> tuple[str, float]:
    """The analyzer's decision at a pause after a second of the fakes' tone: its state and the
    model's probability, from `model` when given."""
    if model is not None:
        analyzer._session = model  # type: ignore[attr-defined]
    analyzer.set_sample_rate(16_000)
    analyzer.append_audio(tone(1.0, 16_000), True)
    state, metrics = await analyzer.analyze_end_of_turn()
    return state.name, getattr(metrics, "probability", -1.0)


def test_smart_turns_threshold_is_pipecats_own_at_its_default_and_moves_the_end_above_it() -> None:
    """`turns.smart_turn_threshold` (smart_turn.py's `ThresholdSmartTurn`, on Pipecat 1.15.0's
    private `_predict_endpoint`): at 0.5, each decision is Pipecat's own, on the model and at
    probabilities around it; at 0.7, a pause the model is 0.6 sure of leaves the turn open,
    which Pipecat's own would end, and one it is 0.71 sure of ends it."""
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

    pipecats = LocalSmartTurnAnalyzerV3(cpu_count=1)
    ours, higher = (
        turn_analyzer(TurnSettings()),
        turn_analyzer(TurnSettings(smart_turn_threshold=0.7)),
    )

    async def run() -> None:
        assert await _decide(ours) == await _decide(pipecats)
        for probability in (0.2, 0.5, 0.5001, 0.6, 0.9):
            heard = await _decide(ours, _Model(probability))
            assert heard == await _decide(pipecats, _Model(probability))
            assert heard[0] == ("COMPLETE" if probability > 0.5 else "INCOMPLETE")
        assert await _decide(higher, _Model(0.6)) == ("INCOMPLETE", 0.6)
        assert await _decide(higher, _Model(0.71)) == ("COMPLETE", 0.71)
        for analyzer in (pipecats, ours, higher):  # each one's model thread
            cleanup: Callable[[], Awaitable[None]] = analyzer.cleanup
            await cleanup()

    asyncio.run(run())


def test_smart_turn_keeps_the_turns_audio_through_a_hold_and_drops_it_at_the_turns_end() -> None:
    """With a hold (`turns.complete_hold_ms`), a pause judged complete keeps the turn's audio
    (smart_turn.py's `keep_turn`, on Pipecat 1.15.0's private `_clear`), so the next judgement
    hears the whole turn; without one it is cleared, as Pipecat's own does. The turn's end
    (`clear`) and the silence fallback drop it either way."""
    from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState

    plain = turn_analyzer(TurnSettings(complete_hold_ms=0))
    held = turn_analyzer(TurnSettings(complete_hold_ms=300))

    def buffered(analyzer: BaseTurnAnalyzer) -> int:
        return len(analyzer._audio_buffer)  # type: ignore[attr-defined]

    async def run() -> None:
        assert await _decide(plain, _Model(0.9)) == ("COMPLETE", 0.9)
        assert (plain.speech_triggered, buffered(plain)) == (False, 0)
        assert await _decide(held, _Model(0.9)) == ("COMPLETE", 0.9)
        assert (held.speech_triggered, buffered(held)) == (True, 1)
        assert await _decide(held, _Model(0.9)) == ("COMPLETE", 0.9)  # the turn went on
        assert buffered(held) == 2  # judged on both seconds
        held.clear()  # type: ignore[no-untyped-call]
        assert (held.speech_triggered, buffered(held)) == (False, 0)
        await _decide(held, _Model(0.2))
        silence = bytes(16_000 * 2)  # a second of it, three times: past the 3 s fallback
        states = [held.append_audio(silence, False) for _ in range(3)]
        assert states[-1] == EndOfTurnState.COMPLETE
        assert (held.speech_triggered, buffered(held)) == (False, 0)
        for analyzer in (plain, held):
            cleanup: Callable[[], Awaitable[None]] = analyzer.cleanup
            await cleanup()

    asyncio.run(run())


def test_each_judgement_the_model_makes_is_logged_with_its_times_and_numbers_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """smart_turn.py's `smart_turn_judged`: the verdict, the model's own time as Pipecat
    measures it, and where the rest of the judgement's time went; nothing for a judgement in
    which no model ran (an empty buffer)."""
    from t2_agentic_voice.core.logging import FIELDS

    caplog.set_level(logging.INFO, logger="t2_agentic_voice")
    analyzer = turn_analyzer(TurnSettings(complete_hold_ms=0))

    async def run() -> None:
        assert await _decide(analyzer, _Model(0.8)) == ("COMPLETE", 0.8)
        await analyzer.analyze_end_of_turn()  # with no hold the verdict cleared its buffer
        cleanup: Callable[[], Awaitable[None]] = analyzer.cleanup
        await cleanup()

    asyncio.run(run())
    (judged,) = [r for r in caplog.records if r.getMessage() == "smart_turn_judged"]
    fields = getattr(judged, FIELDS)
    times = ("model_ms", "wait_ms", "join_ms", "back_ms", "total_ms")
    assert set(fields) == {"complete", "probability", "audio_s", *times}
    assert (fields["complete"], fields["probability"], fields["audio_s"]) == (True, 0.8, 1.0)
    assert all(fields[name] >= 0 for name in ("model_ms", "wait_ms", "back_ms"))
    parts = sum(fields[name] for name in times[:-1])
    assert abs(parts - fields["total_ms"]) <= 0.5
