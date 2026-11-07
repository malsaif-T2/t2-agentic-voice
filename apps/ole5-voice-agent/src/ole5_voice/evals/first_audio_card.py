"""The scorecard of `poe first-audio` (plan 006's registration, T; its scoring is
first_audio_score.py's): what the run was, its totals, its targets, its numbers by where the
time starts and by language, what it spent and each recording, written whole at the run's end
(`close_run`) with its history line (`line_of`, measure_lines.py's `FirstAudioLine`: the totals,
every target, the numbers by where the time starts, each model's requests, the chat model's
among them, and the cost every model's). The targets read every recording together, those timed
from the owner's marked end and those from the speech detector's stop, and the scorecard shows
the two apart (Q18): a dev run's breakdowns by where the time starts and by language, a held-out
run's by where the time starts only, as aggregates. A held-out run holds no recording, no group
of fewer than `HELD_OUT_MIN_ITEMS` items, and no path's times over fewer.
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
from ole5_voice.evals.measure_lines import FirstAudioGroup, FirstAudioLine
from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.overlap_card import AppendLine
from ole5_voice.evals.overlap_score import Target
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
        else PathStats(turns=stats.turns, items=stats.items, no_audio=stats.no_audio)
        for path, stats in totals.paths.items()
    }
    return AudioMetrics.model_validate(totals.model_dump() | {"paths": paths})


def held_out_ends(results: list[AudioResult]) -> dict[str, dict[str, AudioMetrics]]:
    """A held-out run's numbers by where the time starts: each group of `HELD_OUT_MIN_ITEMS`
    items or more, its paths' times withheld as the totals' are; a smaller group left out."""
    groups = breakdowns(results).get("end", {})
    return {"end": {e: _withheld(m) for e, m in groups.items() if m.items >= HELD_OUT_MIN_ITEMS}}


def line_of(card: AudioScorecard) -> FirstAudioLine:
    """The history line of a run (the module's docstring)."""
    run, totals = card.run, card.totals
    stt = [usage for usage in card.spend if usage.model.startswith("whisper")]
    requests = {usage.model: usage.requests for usage in card.spend}
    return FirstAudioLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        agent=run.agent,
        tools=run.tools,
        settings=run.settings,
        split=run.split,
        items=totals.items,
        variants=totals.variants,
        cut=totals.cut,
        failures=totals.failures,
        unanswered=totals.unanswered,
        no_audio=totals.no_audio,
        paths=totals.paths,
        progress_lines=totals.progress_lines,
        progress_median_ms=totals.progress_median_ms,
        progress_late=totals.progress_late,
        targets={target.name: target.holds for target in card.targets},
        ends={
            end: FirstAudioGroup(
                items=m.items, variants=m.variants, paths=m.paths, progress_late=m.progress_late
            )
            for end, m in card.breakdowns.get("end", {}).items()
        },
        phrase_requests=card.phrase_requests,
        requests=requests | {run.settings["llm.model"]: card.chat.requests},
        characters={usage.model: usage.characters for usage in card.spend if usage.characters},
        billed_seconds=sum(usage.billed_s for usage in stt),
        price_per_hour_usd=run.price_per_hour_usd,
        tts_price_per_million_usd=run.tts_price_per_million_usd,
        chat_price_per_million_usd=run.chat_price_per_million_usd,
        cost_usd=card.cost_usd,
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
        targets=targets(kept, held_out=held_out, tail_s=info.tail_s),
        breakdowns=held_out_ends(kept) if held_out else breakdowns(kept),
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
