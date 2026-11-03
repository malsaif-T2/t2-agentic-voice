"""The scorer of `poe eval-timing` (plan 003's registration, T): each variant's timed turn and its
steps, the run's medians and 90th percentiles by step and language, and what the run spent.

The **timed turn** is a variant's first turn that ends at or after its true end (the owner's
mark) minus `TOLERANCE_MS`, E's tolerance. A variant with a turn that ended before that is
**cut** (cut off into two turns or more): it is counted and reported apart, its steps kept, and
left out of the medians, as a variant that failed is. Each step, in ms: the VAD stop delay (the
true end to Silero's stop); Smart Turn's decision (that stop to the turn's end); Whisper's
request (sent to answered); the echo's text ready (Whisper's answer to the heard words'
`Speak`); Orpheus's first byte (sent to its first audio); its leading silence (the audio before
its first sound above the noise floor); the time to first audio (the true end to the cached
frame's first output frame); and the time to the heard words (the true end to Orpheus's first
sound, as it came from the provider). Quantiles are Hyndman and Fan's type 7
(`scorecard.quantile`), as plan 002 took them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice.evals import EchoTiming, TurnTiming
from t2_agentic_voice.events import ModelUsage

from ole5_voice.evals.eot_score import TOLERANCE_MS
from ole5_voice.evals.models import Commit, Device, Language, Model, Name, Sha256, Split
from ole5_voice.evals.runs import Note, Shown
from ole5_voice.evals.scorecard import quantile

# Each step a timed turn gives, in the registration's order.
STEPS: Final = (
    "vad_stop",
    "smart_turn",
    "whisper",
    "echo_ready",
    "orpheus_first_byte",
    "leading_silence",
    "first_audio",
    "heard_words",
)
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
# Why a timing run stopped before its end: the phrase cache failed, the smoke test failed, the
# next variant would pass the cap, or the run was interrupted.
Stopped = Literal["phrases_failed", "smoke_failed", "cap", "interrupted"]


class Steps(Model):
    """One timed turn's steps, in ms, each None when the call gave no time for it."""

    vad_stop: float | None = None
    smart_turn: float | None = None
    whisper: float | None = None
    echo_ready: float | None = None
    orpheus_first_byte: float | None = None
    leading_silence: float | None = None
    first_audio: float | None = None
    heard_words: float | None = None


def _less(later: float | None, earlier: float | None) -> float | None:
    return None if later is None or earlier is None else later - earlier


def steps_of(turn: TurnTiming, true_end_ms: float) -> Steps:
    """`turn`'s steps, against the variant's true end."""
    return Steps(
        vad_stop=_less(turn.speech_stop_ms, true_end_ms),
        smart_turn=_less(turn.end_ms, turn.speech_stop_ms),
        whisper=_less(turn.stt_answered_ms, turn.stt_sent_ms),
        echo_ready=_less(turn.echo_text_ms, turn.stt_answered_ms),
        orpheus_first_byte=_less(turn.tts_first_audio_ms, turn.tts_sent_ms),
        leading_silence=turn.leading_silence_ms,
        first_audio=_less(turn.frame_audio_ms, true_end_ms),
        heard_words=_less(turn.heard_sound_ms, true_end_ms),
    )


class TimingResult(Model):
    """One variant of a timing run: its strata and true end, how many times its call ran (a
    rate-limited one is run again), its last call's turns, whether it was cut, its timed turn's
    place and steps, and the failure its last call met."""

    item: Name
    variant: Name
    split: Split
    language: Language
    device: Device
    true_end_ms: float
    attempts: int = Field(ge=1)
    turns: tuple[TurnTiming, ...]
    cut: bool
    timed_turn: int | None = None  # its place among `turns`
    steps: Steps | None = None
    failure: str | None = None


def judged(timing: EchoTiming, true_end_ms: float) -> tuple[bool, int | None, Steps | None]:
    """Whether `timing` was cut, and its timed turn's place and steps (None when no turn ended
    at or after the true end minus `TOLERANCE_MS`)."""
    ends = [
        (turn.end_ms, place) for place, turn in enumerate(timing.turns) if turn.end_ms is not None
    ]
    cut = any(end < true_end_ms - TOLERANCE_MS for end, _ in ends)
    timed = sorted((end, place) for end, place in ends if end >= true_end_ms - TOLERANCE_MS)
    if not timed:
        return cut, None, None
    place = timed[0][1]
    return cut, place, steps_of(timing.turns[place], true_end_ms)


def failure_of(timing: EchoTiming) -> str | None:
    """The first failure any of `timing`'s turns met."""
    return next((turn.failure for turn in timing.turns if turn.failure is not None), None)


class StepStats(Model):
    """One step's median and 90th percentile, over the timed turns that gave it."""

    turns: int = Field(ge=0)
    median_ms: float | None = None
    p90_ms: float | None = None


class TimingMetrics(Model):
    """The numbers of some variants: how many, how many were cut and how many failed, and each
    step's spread over the others' timed turns."""

    variants: int = Field(ge=0)
    cut_variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    steps: dict[str, StepStats]


def metrics(results: Sequence[TimingResult]) -> TimingMetrics:
    """The numbers of `results`: a cut or failed variant is left out of the steps."""
    kept = [r.steps for r in results if r.steps is not None and not r.cut and r.failure is None]
    steps: dict[str, StepStats] = {}
    for step in STEPS:
        ordered = sorted(value for s in kept if (value := getattr(s, step)) is not None)
        steps[step] = StepStats(
            turns=len(ordered), median_ms=quantile(ordered, 0.5), p90_ms=quantile(ordered, 0.9)
        )
    return TimingMetrics(
        variants=len(results),
        cut_variants=sum(r.cut for r in results),
        failures=sum(r.failure is not None for r in results),
        steps=steps,
    )


def by_language(results: Sequence[TimingResult]) -> dict[str, TimingMetrics]:
    groups: dict[str, list[TimingResult]] = defaultdict(list)
    for result in results:
        groups[result.language].append(result)
    return {language: metrics(group) for language, group in sorted(groups.items())}


def summed(usages: Iterable[ModelUsage]) -> tuple[ModelUsage, ...]:
    """Each model's usage over many calls, in the order the models came: the counts added, the
    headroom the last call reported."""
    totals: dict[str, ModelUsage] = {}
    for usage in usages:
        known = totals.get(usage.model)
        if known is None:
            totals[usage.model] = usage
            continue
        remaining = (usage.remaining_requests, usage.remaining_tokens)
        if remaining == (None, None):
            remaining = (known.remaining_requests, known.remaining_tokens)
        totals[usage.model] = ModelUsage(
            model=usage.model,
            requests=known.requests + usage.requests,
            audio_sent_s=known.audio_sent_s + usage.audio_sent_s,
            billed_s=known.billed_s + usage.billed_s,
            characters=known.characters + usage.characters,
            cache_hits=known.cache_hits + usage.cache_hits,
            remaining_requests=remaining[0],
            remaining_tokens=remaining[1],
        )
    return tuple(totals.values())


def cost(
    usages: Iterable[ModelUsage],
    *,
    stt_model: str,
    price_per_hour_usd: float,
    tts_price_per_million_usd: Mapping[str, float],
) -> float:
    """What `usages` cost: Whisper's billed hours at its price, and each text-to-speech model's
    characters at its price per million (a model with no price costs nothing)."""
    total = 0.0
    for usage in usages:
        if usage.model == stt_model:
            total += usage.billed_s / 3600 * price_per_hour_usd
        else:
            total += usage.characters / 1e6 * tts_price_per_million_usd.get(usage.model, 0.0)
    return total


class TimingRun(Model):
    """What a timing run was: when, at which commit, with which settings, data, padding, pacing
    and prices, and why."""

    name: Name
    started_at: datetime
    commit: Commit
    split: Split
    settings: Shown
    data_digest: Sha256
    lead_s: float = Field(ge=0, allow_inf_nan=False)
    tail_s: float = Field(ge=0, allow_inf_nan=False)
    stt_rpm: int = Field(ge=1)
    tts_rpm: int = Field(ge=1)
    price_per_hour_usd: _Usd
    tts_price_per_million_usd: dict[str, float]
    cap_usd: _Usd
    note: Note


class TimingScorecard(Model):
    """A timing run's scorecard: whether it finished, and why not (`stopped`); the requests the
    phrase cache sent before the first variant; the smoke test's usage, with the headroom Groq
    reported after it (Q17); the totals and the numbers by language; every request's usage and
    the cost; and each variant."""

    run: TimingRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    stopped: Stopped | None = None
    phrase_requests: int = Field(ge=0)
    smoke: tuple[ModelUsage, ...] = ()
    totals: TimingMetrics
    languages: dict[str, TimingMetrics]
    spend: tuple[ModelUsage, ...]
    cost_usd: _Usd
    variants: tuple[TimingResult, ...] = ()
