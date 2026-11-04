"""One call's turn detection (the design's 13; plan 003's decision log): Silero VAD hears when
the caller speaks, and Smart Turn v3.2 decides at each pause whether the turn has ended, both on
the CPU through onnxruntime, with no torch, from the settings' `turns` group.

- `speech_detector` and `turn_analyzer` build the models, Smart Turn with the settings'
  threshold (smart_turn.py's `ThresholdSmartTurn`, which leaves a turn's end as it was at 0.5);
  each loads its ONNX model when it is built, and importing onnxruntime takes 8 to 12 s a
  process (plan 003's appendix, "Changes to the plan's interfaces", item 24), so they import it
  only when called: by voice's entry point, at the runtime's start and, off the event loop, for
  each call (voice/calls.py).
- `turn_processors` builds a call's `VADProcessor` and `UserTurnProcessor` around them.
  Pipecat's interruptions stay off (item 2): the only start strategy is the speech detector's,
  with `enable_interruptions=False`, so a turn's start broadcasts no `InterruptionFrame` and
  only the session stops the agent's speech. The stop strategy is Smart Turn's, set
  explicitly with `wait_for_transcript=False` (Pipecat 1.15.0 defaults it on, and a turn's end
  would then come only with the transcript, or at its 5 s stop timeout: the spike's run D), so a
  turn's end is the analyzer's alone and the session waits for the transcript itself. With
  `turns.complete_hold_ms` above 0 it is turn_hold.py's `HeldTurnStop`, the analyzer's verdict
  held that long and dropped when the speech resumes, Smart Turn keeping the turn's audio
  through it; at 0 it is Pipecat's own strategy, so a turn's end is as it was. With
  `turns.smart_turn` off, every pause the detector hears ends the turn, with no hold.
  `turns.max_silence_ms` is Pipecat's stop timeout, the fallback that ends a turn whatever
  decides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import (
    SpeechTimeoutUserTurnStopStrategy,
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_stop.base_user_turn_stop_strategy import BaseUserTurnStopStrategy
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import UserTurnStrategies, UserTurnStrategiesParams

from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.turn_hold import HeldTurnStop

if TYPE_CHECKING:  # their modules import onnxruntime: imported when a model is built
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADAnalyzer


def vad_params(turns: TurnSettings) -> VADParams:
    """The speech detector's parameters from the `turns` settings."""
    return VADParams(
        confidence=turns.vad_confidence,
        start_secs=turns.vad_start_ms / 1000,
        stop_secs=turns.vad_stop_ms / 1000,
        min_volume=turns.vad_min_volume,
    )


def speech_detector(turns: TurnSettings) -> VADAnalyzer:
    """A Silero VAD with the `turns` settings, its model loaded on the CPU for one call."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer

    return SileroVADAnalyzer(params=vad_params(turns))


def turn_analyzer(turns: TurnSettings) -> BaseTurnAnalyzer:
    """A Smart Turn v3.2 with the `turns` settings, its threshold among them, keeping a turn's
    audio through a hold (`complete_hold_ms`), its model loaded on the CPU for one call."""
    from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams

    from t2_agentic_voice.voice.smart_turn import ThresholdSmartTurn

    params = SmartTurnParams(
        stop_secs=turns.smart_turn_stop_ms / 1000,
        pre_speech_ms=turns.smart_turn_pre_speech_ms,
        max_duration_secs=turns.smart_turn_max_duration_s,
    )
    return ThresholdSmartTurn(
        threshold=turns.smart_turn_threshold,
        keep_turn=turns.complete_hold_ms > 0,
        params=params,
        cpu_count=1,
    )


def turn_processors(
    detector: VADAnalyzer, analyzer: BaseTurnAnalyzer | None, turns: TurnSettings
) -> tuple[FrameProcessor, FrameProcessor]:
    """A call's speech detection and turn decision, in pipeline order: `detector` in a
    `VADProcessor`, then a `UserTurnProcessor` whose turns `analyzer` ends (every pause, with
    none), after the `complete_hold_ms` hold."""
    stop: BaseUserTurnStopStrategy
    if analyzer is None:
        stop = SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.0, wait_for_transcript=False)
    elif turns.complete_hold_ms > 0:
        stop = HeldTurnStop(
            hold_s=turns.complete_hold_ms / 1000, turn_analyzer=analyzer, wait_for_transcript=False
        )
    else:
        stop = TurnAnalyzerUserTurnStopStrategy(turn_analyzer=analyzer, wait_for_transcript=False)
    strategies = UserTurnStrategies(
        start=[VADUserTurnStartStrategy(enable_interruptions=False)], stop=[stop]
    )
    vad = VADProcessor(vad_analyzer=detector, name="t2v-vad")
    user_turns = UserTurnProcessor(
        user_turn_strategies=strategies,
        user_turn_strategies_params=UserTurnStrategiesParams(),
        user_turn_stop_timeout=turns.max_silence_ms / 1000,
        name="t2v-turns",
    )
    return vad, user_turns
