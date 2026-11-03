"""The scorecard of `poe overlap` (plan 005's registration, the arm O; its scoring is
overlap_score.py's): what the run was, its totals, breakdowns and targets, its spend, and each
variant, none for a held-out run, whose numbers are aggregates only (`HELD_OUT_MIN_ITEMS`), as
`poe eot`'s are: no variant and no item named, and a stratum value covering fewer items pooled
into `other`, itself left out when it too covers fewer. Strict, as every scorecard: one read back
is checked as it is read. `close_run` writes it whole at a run's end, and for a run of the replay
its history line (`line_of`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import Field, model_validator
from t2_agentic_voice import get_logger

from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import OTHER, Commit, Model, Name, Sha256, Split
from ole5_voice.evals.overlap_run import Progress, Stopped
from ole5_voice.evals.overlap_score import OverlapMetrics, OverlapResult, Target, metrics, targets
from ole5_voice.evals.run_lines import AnyLine, OverlapCount, OverlapLine
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, SCORECARD_FILE, Note, Shown, cost_usd

log = get_logger(__name__)
AppendLine = Callable[[AnyLine, Path], None]  # `history.append_line`, or a test's


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
    stopped: Stopped | None = None
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


def close_run(
    info: OverlapRun,
    progress: Progress,
    total: int,
    spent: tuple[int, float],
    out: Path,
    data: Path,
    append_line: AppendLine,
) -> int:
    """The scorecard, and for a run of the replay its history line; 0 when complete."""
    complete = progress.stopped is None and len(progress.results) == total
    held_out = info.split == "held-out"
    kept = progress.results if complete or not held_out else []
    requests, billed = spent
    card = OverlapScorecard(
        run=info,
        complete=complete,
        stopped=progress.stopped,
        totals=metrics(kept),
        breakdowns=breakdowns(kept, held_out=held_out),
        targets=targets(kept, held_out=held_out),
        requests=requests,
        billed_seconds=billed,
        cost_usd=cost_usd(billed, info.price_per_hour_usd or 0.0),
        variants=() if held_out else tuple(kept),
    )
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((card.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)
    if info.answerer == "pipeline":
        line = line_of(card)
        append_line(line, data / HISTORY_FILE)
        append_line(line, out / HISTORY_FILE)
    totals = card.totals
    held = sum(target.holds is True for target in card.targets)
    log.info(
        "run_finished",
        complete=complete,
        variants=totals.variants,
        right=totals.right,
        targets_held=f"{held} of {len(card.targets)}",
        cost_usd=card.cost_usd,
    )
    return 0 if complete else 1


def line_of(card: OverlapScorecard) -> OverlapLine:
    """The history line of an overlap run's scorecard."""
    run, totals = card.run, card.totals
    found = {target.name: target for target in card.targets}
    return OverlapLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        answerer=run.answerer,
        settings=run.settings,
        split=run.split,
        items=totals.items,
        variants=totals.variants,
        right=totals.right,
        stop_median_ms=found["stop_word_median_ms"].value,
        stop_p90_ms=found["stop_word_p90_ms"].value,
        requests_max=totals.requests_max,
        targets={name: target.holds for name, target in found.items()},
        breakdowns={
            stratum: {
                value: OverlapCount.model_validate(m, from_attributes=True)
                for value, m in values.items()
            }
            for stratum, values in card.breakdowns.items()
            if stratum != "item"
        },
        requests=card.requests,
        billed_seconds=card.billed_seconds,
        price_per_hour_usd=run.price_per_hour_usd or 0.0,
        cost_usd=card.cost_usd,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )
