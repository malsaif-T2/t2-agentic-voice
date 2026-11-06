"""The scorecard of `poe first-audio` (plan 006's registration, T; its scoring is
first_audio_score.py's): what the run was, its totals, its targets, its numbers by where the
time starts and by language, what it spent and each recording, written whole at the run's end
(`close_run`) with its history line (`line_of`). A held-out run's holds aggregates only: no
recording, no breakdown, and no path's times over fewer than `HELD_OUT_MIN_ITEMS` items. The
history line is a timing line (run_lines.py's `TimingLine`, whose fields hold a run of times by
step): its steps are each path's median and 90th percentile and the progress lines' median, its
requests and characters each model's, and its cost every model's, the chat model's included.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from t2_agentic_voice import get_logger
from t2_agentic_voice.events import ModelUsage

from ole5_voice.evals.first_audio_run import Measuring
from ole5_voice.evals.first_audio_score import (
    AudioMetrics,
    AudioResult,
    ChatSpend,
    PathStats,
    breakdowns,
    metrics,
    targets,
)
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.overlap_card import AppendLine
from ole5_voice.evals.overlap_score import Target
from ole5_voice.evals.run_lines import TimingLine
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, SCORECARD_FILE, Note, Plain, Shown
from ole5_voice.evals.timing_score import summed

_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
# Why a run stopped before its last recording: the phrase cache failed, the smoke test failed,
# the next recording would pass the cap or a model's day, or the run was interrupted.
Stopped = Literal["phrases_failed", "smoke_failed", "cap", "day_limit", "interrupted"]
log = get_logger(__name__)


class AudioRun(Model):
    """What a run was: when, at which commit, on which split, with which agent (its factory,
    and whether its tools were left out), settings, padding, prices and cap, and why."""

    name: Name
    started_at: datetime
    commit: Commit
    split: Split
    agent: Plain
    tools: bool
    settings: Shown
    data_digest: Sha256
    lead_s: float = Field(ge=0, allow_inf_nan=False)
    tail_s: float = Field(ge=0, allow_inf_nan=False)
    price_per_hour_usd: _Usd
    tts_price_per_million_usd: dict[str, float]
    chat_price_per_million_usd: dict[str, float]  # input, cached and output
    cap_usd: _Usd
    note: Note


class AudioScorecard(Model):
    """A run's scorecard: whether it finished, and why not; the phrase cache's requests; the
    totals, targets and breakdowns; each model's usage, the chat model's and the cost; and each
    recording, none for a held-out run."""

    run: AudioRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    stopped: Stopped | None = None
    phrase_requests: int = Field(ge=0)
    totals: AudioMetrics
    targets: tuple[Target, ...]
    breakdowns: dict[str, dict[str, AudioMetrics]] = Field(default_factory=dict)
    spend: tuple[ModelUsage, ...]
    chat: ChatSpend
    cost_usd: _Usd
    variants: tuple[AudioResult, ...] = ()


def _withheld(totals: AudioMetrics) -> AudioMetrics:
    """A held-out run's totals: each path's times over too few items left out."""
    paths = {
        path: stats
        if stats.items >= HELD_OUT_MIN_ITEMS
        else PathStats(turns=stats.turns, items=stats.items)
        for path, stats in totals.paths.items()
    }
    return AudioMetrics.model_validate(totals.model_dump() | {"paths": paths})


def line_of(card: AudioScorecard) -> TimingLine:
    """The history line of a run (the module's docstring)."""
    run, totals = card.run, card.totals
    stt = [usage for usage in card.spend if usage.model.startswith("whisper")]
    steps = {
        f"{path}{suffix}": value
        for path, stats in totals.paths.items()
        for suffix, value in (("", stats.median_ms), ("_p90", stats.p90_ms))
    }
    requests = {usage.model: usage.requests for usage in card.spend}
    return TimingLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        settings=run.settings,
        split=run.split,
        variants=totals.variants,
        cut_variants=totals.cut,
        failures=totals.failures,
        phrase_requests=card.phrase_requests,
        requests=requests | {run.settings["llm.model"]: card.chat.requests},
        characters={usage.model: usage.characters for usage in card.spend if usage.characters},
        billed_seconds=sum(usage.billed_s for usage in stt),
        price_per_hour_usd=run.price_per_hour_usd,
        tts_price_per_million_usd=run.tts_price_per_million_usd,
        cost_usd=card.cost_usd,
        medians_ms=steps | {"progress": totals.progress_median_ms},
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )


def close_run(
    info: AudioRun,
    found: list[AudioResult],
    stopped: Stopped | None,
    total: int,
    measuring: Measuring,
    out: Path,
    data: Path,
    append_line: AppendLine,
) -> int:
    """The scorecard and its history line; 0 when the run is complete."""
    complete = stopped is None and len(found) == total
    held_out = info.split == "held-out"
    kept = found if complete or not held_out else []  # an unfinished held-out run keeps none
    chats = measuring.chats
    card = AudioScorecard(
        run=info,
        complete=complete,
        stopped=stopped,
        phrase_requests=measuring.phrase_requests,
        totals=_withheld(metrics(kept)) if held_out else metrics(kept),
        targets=targets(kept, held_out=held_out),
        breakdowns={} if held_out else breakdowns(kept),
        spend=summed(measuring.usages),
        chat=ChatSpend(
            requests=sum(c.requests for c in chats),
            input_tokens=sum(c.input_tokens for c in chats),
            cached_tokens=sum(c.cached_tokens for c in chats),
            output_tokens=sum(c.output_tokens for c in chats),
        ),
        cost_usd=measuring.spent_usd,
        variants=() if held_out else tuple(kept),
    )
    partial = out / f".{SCORECARD_FILE}.partial"
    partial.write_bytes((card.model_dump_json(indent=2) + "\n").encode("utf-8"))
    partial.replace(out / SCORECARD_FILE)
    line = line_of(card)
    append_line(line, data / HISTORY_FILE)
    append_line(line, out / HISTORY_FILE)
    held = sum(target.holds is True for target in card.targets)
    log.info(
        "run_finished",
        complete=complete,
        variants=card.totals.variants,
        targets_held=f"{held} of {len(card.targets)}",
        cost_usd=card.cost_usd,
    )
    return 0 if complete else 1
