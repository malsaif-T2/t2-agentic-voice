"""The scorer of `poe eot` (plan 003's registration, E): each variant's turn ends judged against
its true end, and the run's numbers.

A variant's true end is the owner's mark on its waveform (`Variant.turn_ends_ms`, the paused
requests), or, for the secondary set, which has no mark, the end of the last speech Silero found
in the clip (the last turn's speech stop: the agent's proxy). Its first turn end decides it: a
**cut-off** when it falls more than `TOLERANCE_MS` before the true end (a mark clicked on a
waveform); else a **miss** when no turn end comes within `MISS_WINDOW_MS` after the true end;
else it is timed, its **end-of-turn delay** the first turn end at or after the true end minus
`TOLERANCE_MS`, less the true end, with its parts, the **VAD stop delay** (to Silero's stop) and
**Smart Turn's decision** (from that stop to the turn end). The secondary set's VAD stop delay
is not given: it would measure Silero against itself. Medians and 90th percentiles are taken as
plan 002 took them (Hyndman and Fan's type 7, `scorecard.quantile`).

A held-out run's numbers are aggregates only (`HELD_OUT_MIN_ITEMS`), as `poe eval`'s are: no
variant and no item named, and a stratum value covering fewer items pooled into `other`, itself
left out when it too covers fewer.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.models import (
    OTHER,
    Commit,
    Device,
    Kind,
    Language,
    Model,
    Name,
    Sha256,
    Split,
)
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Note, Shown
from ole5_voice.evals.scorecard import quantile

TOLERANCE_MS: Final = 300.0  # a turn end this much before the true end still counts as on it
MISS_WINDOW_MS: Final = 4000.0  # no turn end this long after the true end is a miss
# Which set a variant is of: the paused requests, with the owner's mark, or the secondary set.
EotSet = Literal["paused", "secondary"]
# A variant's verdict.
Verdict = Literal["cut_off", "miss", "timed"]


class Decision(Model):
    """One turn end as an answerer gave it, in ms from the clip's start: when the speech
    detector last heard the speech stop before it, and when the turn ended (testing's
    `TurnEnd`)."""

    speech_stop_ms: float = Field(allow_inf_nan=False)
    end_ms: float = Field(allow_inf_nan=False)


class Judged(Model):
    """One variant's turn ends judged against its true end (None for a secondary variant in
    which no speech was found: a miss). `early` counts the turn ends more than `TOLERANCE_MS`
    before it; the delays are set for a timed variant only, the VAD stop delay only for the
    paused set."""

    true_end_ms: float | None
    verdict: Verdict
    early: int = Field(ge=0)
    delay_ms: float | None = None
    vad_stop_ms: float | None = None
    decision_ms: float | None = None


def judge(ends: Sequence[Decision], true_end_ms: float | None, *, labelled: bool) -> Judged:
    """`ends` judged against `true_end_ms`, the owner's mark when `labelled`, else the proxy: by
    the first turn end, whatever order they are given in."""
    if true_end_ms is None:
        return Judged(true_end_ms=None, verdict="miss", early=0)
    ordered = sorted(ends, key=lambda end: end.end_ms)
    early = [end for end in ordered if end.end_ms < true_end_ms - TOLERANCE_MS]
    if early:
        return Judged(true_end_ms=true_end_ms, verdict="cut_off", early=len(early))
    timed = ordered[0] if ordered else None
    if timed is None or timed.end_ms > true_end_ms + MISS_WINDOW_MS:
        return Judged(true_end_ms=true_end_ms, verdict="miss", early=len(early))
    return Judged(
        true_end_ms=true_end_ms,
        verdict="timed",
        early=len(early),
        delay_ms=timed.end_ms - true_end_ms,
        vad_stop_ms=timed.speech_stop_ms - true_end_ms if labelled else None,
        decision_ms=timed.end_ms - timed.speech_stop_ms,
    )


def proxy_end(ends: Sequence[Decision]) -> float | None:
    """The secondary set's true end: the last speech stop Silero found (the last turn's), None
    when it found no speech."""
    return max((end.speech_stop_ms for end in ends), default=None)


class EotResult(Model):
    """One variant of an end-of-turn run: its strata, its set, the turn ends the answerer gave
    and how they were judged."""

    item: Name
    variant: Name
    split: Split
    kind: Kind
    language: Language
    device: Device
    set: EotSet
    ends: tuple[Decision, ...]
    judged: Judged


class EotMetrics(Model):
    """The numbers of one set, or of one stratum value of it: its items and variants, its
    cut-offs and misses, and each delay's median and 90th percentile over its timed variants."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    cut_offs: int = Field(ge=0)
    misses: int = Field(ge=0)
    delay_median_ms: float | None = None
    delay_p90_ms: float | None = None
    vad_stop_median_ms: float | None = None
    vad_stop_p90_ms: float | None = None
    decision_median_ms: float | None = None
    decision_p90_ms: float | None = None


class EotSetCard(Model):
    """One set's totals and breakdowns: by language and device, and, in a dev run, by item."""

    totals: EotMetrics
    breakdowns: dict[str, dict[str, EotMetrics]]


class EotRun(Model):
    """What an end-of-turn run was: when, at which commit, with which answerer, settings and
    data, with how much silence fed before and after each clip, and why."""

    name: Name
    started_at: datetime
    commit: Commit
    answerer: Name
    split: Split
    settings: Shown
    data_digest: Sha256
    lead_s: float = Field(ge=0, allow_inf_nan=False)
    tail_s: float = Field(ge=0, allow_inf_nan=False)
    note: Note


class EotScorecard(Model):
    """An end-of-turn run's scorecard: the paused requests' set, the secondary set's when it
    ran, and each variant, none for a held-out run, refused as it is read."""

    run: EotRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    paused: EotSetCard
    secondary: EotSetCard | None = None
    variants: tuple[EotResult, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        if self.run.split == "held-out" and (self.variants or self.secondary is not None):
            raise ValueError("a held-out run's scorecard holds the paused requests' aggregates")
        cards = [self.paused] + ([self.secondary] if self.secondary else [])
        groups = [m.items for card in cards for v in card.breakdowns.values() for m in v.values()]
        if self.run.split == "held-out" and any(n < HELD_OUT_MIN_ITEMS for n in groups):
            raise ValueError(
                f"a held-out run's groups each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        return self


_STRATA: Final[dict[str, Callable[[EotResult], str]]] = {
    "language": lambda result: result.language,
    "device": lambda result: result.device,
    "item": lambda result: result.item,
}


def metrics(results: Sequence[EotResult]) -> EotMetrics:
    """The numbers of `results`."""
    timed = [r.judged for r in results if r.judged.verdict == "timed"]

    def spread(values: Iterable[float | None]) -> tuple[float | None, float | None]:
        ordered = sorted(value for value in values if value is not None)
        return quantile(ordered, 0.5), quantile(ordered, 0.9)

    delay, vad, decision = (
        spread(getattr(j, name) for j in timed)
        for name in ("delay_ms", "vad_stop_ms", "decision_ms")
    )
    return EotMetrics(
        items=len({result.item for result in results}),
        variants=len(results),
        cut_offs=sum(r.judged.verdict == "cut_off" for r in results),
        misses=sum(r.judged.verdict == "miss" for r in results),
        delay_median_ms=delay[0],
        delay_p90_ms=delay[1],
        vad_stop_median_ms=vad[0],
        vad_stop_p90_ms=vad[1],
        decision_median_ms=decision[0],
        decision_p90_ms=decision[1],
    )


def set_card(results: Sequence[EotResult], *, held_out: bool) -> EotSetCard:
    """One set's totals and breakdowns; a held-out run's with no item and its small groups
    pooled."""
    breakdowns: dict[str, dict[str, EotMetrics]] = {}
    for stratum, key in _STRATA.items():
        if held_out and stratum == "item":
            continue
        groups: dict[str, list[EotResult]] = defaultdict(list)
        for result in results:
            groups[key(result)].append(result)
        if held_out:
            groups = _pooled(groups)
        breakdowns[stratum] = {value: metrics(group) for value, group in sorted(groups.items())}
    return EotSetCard(totals=metrics(results), breakdowns=breakdowns)


def _pooled(groups: dict[str, list[EotResult]]) -> dict[str, list[EotResult]]:
    """Each group of `HELD_OUT_MIN_ITEMS` items or more, and the others pooled as `other`, left
    out when it too covers fewer."""
    kept = {value: group for value, group in groups.items() if _items(group) >= HELD_OUT_MIN_ITEMS}
    small = [result for value, group in groups.items() if value not in kept for result in group]
    if _items(small) >= HELD_OUT_MIN_ITEMS:
        kept[OTHER] = small
    return kept


def _items(results: Iterable[EotResult]) -> int:
    return len({result.item for result in results})
