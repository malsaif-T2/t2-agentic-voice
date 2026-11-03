"""The scorecard of `poe overlap` (plan 005's registration, the arm O; its scoring is
overlap_score.py's): what the run was, its totals, breakdowns and targets, its spend, and each
variant, none for a held-out run, whose numbers are aggregates only (`HELD_OUT_MIN_ITEMS`), as
`poe eot`'s are: no variant and no item named, and a stratum value covering fewer items pooled
into `other`, itself left out when it too covers fewer. Strict, as every scorecard: one read back
is checked as it is read.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.models import OTHER, Commit, Model, Name, Sha256, Split
from ole5_voice.evals.overlap_score import OverlapMetrics, OverlapResult, Target, metrics
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Note, Shown


class OverlapRun(Model):
    """What an overlap run was: when, at which commit, with which answerer, settings and data;
    how far into the reply each clip was fed and the silence after it; the Whisper requests a
    minute it was paced at, its price and cap (none for the reference); and why."""

    name: Name
    started_at: datetime
    commit: Commit
    answerer: Name
    split: Split
    settings: Shown
    data_digest: Sha256
    at_s: float = Field(ge=0, allow_inf_nan=False)
    tail_s: float = Field(ge=0, allow_inf_nan=False)
    stt_rpm: int = Field(ge=1)
    price_per_hour_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cap_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    note: Note


class OverlapScorecard(Model):
    """An overlap run's scorecard: its totals, breakdowns and targets; why it stopped early, if
    it did; its requests, billed seconds and cost, every call's; and each variant, none for a
    held-out run, refused as it is read."""

    run: OverlapRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    stopped: Literal["cap", "interrupted"] | None = None
    totals: OverlapMetrics
    breakdowns: dict[str, dict[str, OverlapMetrics]]
    targets: tuple[Target, ...]
    requests: int = Field(ge=0)
    billed_seconds: float = Field(ge=0, allow_inf_nan=False)
    cost_usd: float = Field(ge=0, allow_inf_nan=False)
    variants: tuple[OverlapResult, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        if self.run.split != "held-out":
            return self
        groups = [m.items for values in self.breakdowns.values() for m in values.values()]
        if self.variants or "item" in self.breakdowns:
            raise ValueError("a held-out run's scorecard holds aggregates only")
        if any(n < HELD_OUT_MIN_ITEMS for n in groups):
            raise ValueError(
                f"a held-out run's groups each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        return self


_STRATA: Final[dict[str, Callable[[OverlapResult], str]]] = {
    "kind": lambda result: result.kind,
    "language": lambda result: result.language,
    "device": lambda result: result.device,
    "item": lambda result: result.item,
}


def breakdowns(
    results: Sequence[OverlapResult], *, held_out: bool
) -> dict[str, dict[str, OverlapMetrics]]:
    """The numbers by kind, language and device, and in a dev run by item; a held-out run's
    small groups pooled into `other`, itself left out when it too covers fewer items."""
    found: dict[str, dict[str, OverlapMetrics]] = {}
    for stratum, key in _STRATA.items():
        if held_out and stratum == "item":
            continue
        groups: dict[str, list[OverlapResult]] = defaultdict(list)
        for result in results:
            groups[key(result)].append(result)
        if held_out:
            groups = _pooled(groups)
        found[stratum] = {value: metrics(group) for value, group in sorted(groups.items())}
    return found


def _pooled(groups: dict[str, list[OverlapResult]]) -> dict[str, list[OverlapResult]]:
    kept = {value: group for value, group in groups.items() if _items(group) >= HELD_OUT_MIN_ITEMS}
    small = [result for value, group in groups.items() if value not in kept for result in group]
    if _items(small) >= HELD_OUT_MIN_ITEMS:
        kept[OTHER] = small
    return kept


def _items(results: Iterable[OverlapResult]) -> int:
    return len({result.item for result in results})
