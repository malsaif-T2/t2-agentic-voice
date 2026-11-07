"""The scorecard of `poe uncertain` (plan 006's registration, U; its scoring is
uncertain_score.py's): what the run was, the rule's and the arm's numbers, the keep rule, the
arm's numbers by kind and language, its spend and each overlap judged, written whole at the run's
end (`close_run`) with its history line (`line_of`). The history line is an overlap line
(run_lines.py's `OverlapLine`), whose fields hold a run of verdicts on overlaps: its answerer is
`uncertain`, its numbers are the arm's, and its targets are the keep rule's three parts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import Field
from t2_agentic_voice import get_logger

from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import Commit, Model, Name, Sha256
from ole5_voice.evals.overlap_card import AppendLine
from ole5_voice.evals.run_lines import OverlapCount, OverlapLine
from ole5_voice.evals.runs import SCORECARD_FILE, Note, Plain, Shown
from ole5_voice.evals.uncertain_run import Asking, Found, Stopped
from ole5_voice.evals.uncertain_score import (
    ArmMetrics,
    KeepRule,
    UncertainOverlap,
    UncertainResult,
    keep_rule,
    metrics,
)

_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_STRATA: Final[dict[str, Callable[[UncertainOverlap], str]]] = {
    "kind": lambda overlap: overlap.kind,
    "language": lambda overlap: overlap.language,
}
log = get_logger(__name__)


def breakdowns(results: Sequence[UncertainResult]) -> dict[str, dict[str, ArmMetrics]]:
    """The arm's numbers by kind and by language."""
    found: dict[str, dict[str, ArmMetrics]] = {}
    for stratum, key in _STRATA.items():
        groups: dict[str, list[UncertainResult]] = defaultdict(list)
        for result in results:
            groups[key(result.overlap)].append(result)
        found[stratum] = {v: metrics(g, arm=True) for v, g in sorted(groups.items())}
    return found


class UncertainRun(Model):
    """What a run was: when, at which commit, on which stored overlap run (its name, commit and
    the digest of its scorecard file), how many of its overlaps were judged again under this
    commit's rule and how many of those were not reproduced (uncertain_rejudge.py), with which
    model and settings, prices (USD per million tokens), cap and pacing, and why."""

    name: Name
    started_at: datetime
    commit: Commit
    source: Name
    source_commit: Commit
    data_digest: Sha256
    rejudged: int = Field(default=0, ge=0)
    unmatched: int = Field(default=0, ge=0)
    model: Plain
    settings: Shown
    price_input_usd: _Usd
    price_output_usd: _Usd
    price_cached_usd: _Usd
    cap_usd: _Usd
    rpm: int = Field(ge=1)
    day_requests: int = Field(ge=1)
    note: Note


class UncertainScorecard(Model):
    """A run's scorecard: whether it finished, and why not; the rule's and the arm's numbers,
    the keep rule, the arm's numbers by kind and language, every request and token it sent and
    its cost; and each overlap judged."""

    run: UncertainRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    stopped: Stopped | None = None
    rule: ArmMetrics
    arm: ArmMetrics
    keep: KeepRule
    breakdowns: dict[str, dict[str, ArmMetrics]]
    requests: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: _Usd
    results: tuple[UncertainResult, ...] = ()


def line_of(card: UncertainScorecard) -> OverlapLine:
    """The history line of a run (the module's docstring): it sends no audio, so its billed
    seconds and price per hour are 0, and its cost is the tokens'."""
    run, arm, keep = card.run, card.arm, card.keep
    return OverlapLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        answerer="uncertain",
        settings=run.settings,
        split="dev",
        items=arm.items,
        variants=arm.variants,
        failed=arm.failed,
        right=arm.right,
        stop_median_ms=None,
        stop_p90_ms=None,
        requests_max=None,
        targets={
            "raises_right": keep.raises_right,
            "listening_no_more": keep.listening_no_more,
            "answers_in_time": keep.answers_in_time,
        },
        breakdowns={
            stratum: {
                value: OverlapCount.model_validate(m, from_attributes=True)
                for value, m in values.items()
            }
            for stratum, values in card.breakdowns.items()
        },
        requests=card.requests,
        billed_seconds=0.0,
        price_per_hour_usd=0.0,
        cost_usd=card.cost_usd,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )


def close_run(
    info: UncertainRun,
    found: Found,
    complete: bool,
    asking: Asking,
    out: Path,
    data: Path,
    append_line: AppendLine,
) -> int:
    """The scorecard and its history line; 0 when the run is complete."""
    results = found.results
    card = UncertainScorecard(
        run=info,
        complete=complete,
        stopped=found.stopped,
        rule=metrics(results, arm=False),
        arm=metrics(results, arm=True),
        keep=keep_rule(results),
        breakdowns=breakdowns(results),
        requests=asking.requests,
        input_tokens=asking.input_tokens,
        output_tokens=asking.output_tokens,
        cost_usd=asking.spent_usd,
        results=tuple(results),
    )
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((card.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)
    line = line_of(card)
    append_line(line, data / HISTORY_FILE)
    append_line(line, out / HISTORY_FILE)
    keep = card.keep
    log.info(
        "run_finished",
        complete=complete,
        overlaps=card.arm.variants,
        rule_right=card.rule.right,
        arm_right=card.arm.right,
        p=keep.p,
        kept=keep.kept,
        cost_usd=card.cost_usd,
    )
    return 0 if complete else 1
