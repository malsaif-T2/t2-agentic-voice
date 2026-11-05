"""The `turns` group: when the caller has started and finished speaking.

The defaults are the starting values of plan 003's decision log: Silero's `VADParams` defaults
(confidence 0.7, start and end 200 ms, minimum volume 0.6) and Smart Turn v3.2's documented ones
(3 s, 500 ms of speech before, 8 s at most, and its 0.5 threshold), with the same 3 s as the
fallback end of a turn; and one tuned, a hold of 600 ms after Smart Turn's "complete" (plan
005's E, its arm Ec, kept by the owner's ruling and confirmed on held-out; voice/turn_hold.py).
Each move of a default is a behaviour change, made only on a registered measurement (the
design's 5.4; GP-18).
"""

from __future__ import annotations

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

# The longest hold after Smart Turn's "complete" (`complete_hold_ms`): above the owner's bound on
# how much later a turn may end (plan 005's Q8, 600 ms) and well under the 3 s fallbacks.
MAX_COMPLETE_HOLD_MS = 1000


class TurnSettings(Group):
    """Turn-taking: the speech detector (Silero VAD) and the end-of-turn model (Smart Turn)."""

    vad_confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
        description="How sure the speech detector must be that a frame is speech, from 0 to 1.",
    )
    vad_start_ms: int = Field(
        default=200,
        gt=0,
        description="How long speech must last before the detector says the caller started.",
    )
    vad_stop_ms: int = Field(
        default=200,
        gt=0,
        description="How long a silence must last before the detector says the caller paused.",
    )
    vad_min_volume: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="The quietest a frame may be and still count as speech, from 0 to 1.",
    )
    smart_turn: bool = Field(
        default=True,
        description=(
            "Whether Smart Turn decides, at each pause, if the caller has finished; off, every "
            "pause the detector hears ends the turn."
        ),
    )
    smart_turn_threshold: float = Field(
        default=0.5,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description=(
            "How sure Smart Turn must be that the caller has finished, from 0 to 1: a pause ends "
            "the turn when its probability is above this. 0.5, Smart Turn's own, leaves a "
            "turn's end as it was."
        ),
    )
    complete_hold_ms: int = Field(
        default=600,
        ge=0,
        le=MAX_COMPLETE_HOLD_MS,
        description=(
            "How long a turn Smart Turn judged finished waits before it ends: speech that "
            "resumes within it cancels the end, and the turn goes on. 600 by plan 005's "
            "registered E (its arm Ec, the owner's ruling), which changes only on another "
            "registered measurement (GP-18); 0 ends the turn at Smart Turn's verdict. The "
            "speech detector's pause, which an interruption waits on, is never delayed."
        ),
    )
    smart_turn_stop_ms: int = Field(
        default=3000,
        gt=0,
        description="The silence after which Smart Turn ends the turn whatever it heard.",
    )
    smart_turn_pre_speech_ms: int = Field(
        default=500,
        ge=0,
        description="How much audio before the speech started Smart Turn hears with it.",
    )
    smart_turn_max_duration_s: float = Field(
        default=8.0,
        gt=0,
        allow_inf_nan=False,
        description="The most audio of a turn Smart Turn hears, its latest part.",
    )
    max_silence_ms: int = Field(
        default=3000,
        gt=0,
        description="The fallback end of a turn: a silence this long ends it, whatever decides.",
    )
