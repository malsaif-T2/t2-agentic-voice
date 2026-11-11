"""The history lines of runs U and T (plan 006's registration), each a kind of its own beside
run_lines.py's, since the lines they first borrowed could not hold a number the registration
reads: `UncertainLine` for a `poe uncertain` run, with U0's right verdicts and listening sounds
stopped beside the arm's, the arm's time to an answer and the keep rule (an overlap line holds
the arm's numbers alone); and `FirstAudioLine` for a `poe first-audio` run, with each path's
times, the replies whose progress line began late, every target, and the two starts of time
apart (Q18: the owner's marked end, `label`, and the speech detector's stop, `detector`), where
a timing line holds medians alone, and, for a run with the clause cache (run I's arm), its
numbers (first_audio_cache.py's `ClauseSummary`). Each counts its requests by model, so a later
run's pacers start the day's count from them (`run_folder.requests_today`).

Strict as every history line: a held-out run's groups each cover at least `HELD_OUT_MIN_ITEMS`
items, and a secret setting is shown only as set or not set.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.first_audio_cache import ClauseSummary
from ole5_voice.evals.first_audio_score import PathStats, ReplyPath
from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Note, Plain, Shown

ModelName = Annotated[Plain, Field(min_length=1, max_length=128)]
_Ms = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class UncertainCount(Model):
    """One verdict's numbers over the overlaps a run of U judged (uncertain_score.py's
    `ArmMetrics`): right verdicts, the stops it should make and made, the go-ons it should leave
    and stopped, the listening sounds it stopped, the model's unclear answers and its time to
    an answer (the arm's only)."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    failed: int = Field(ge=0)
    right: int = Field(ge=0)
    should_stop: int = Field(ge=0)
    stopped: int = Field(ge=0)
    should_go_on: int = Field(ge=0)
    false_stops: int = Field(ge=0)
    listening: int = Field(ge=0)
    listening_stops: int = Field(ge=0)
    unclear: int = Field(default=0, ge=0)
    answer_median_ms: _Ms | None = None
    answer_p90_ms: _Ms | None = None


class UncertainLine(Model):
    """One line of `history.jsonl` for a `poe uncertain` run (the module's docstring): the
    stored overlap run it read, its model and settings, the rule's numbers (U0) and the arm's,
    the sign test's items and p, whether each part of the keep rule held and the arm is kept,
    the arm's numbers by stratum value, and its requests, tokens, prices and cost."""

    kind: Literal["uncertain"] = "uncertain"
    time: datetime
    commit: Commit
    run: Name
    source: Name
    model: ModelName
    settings: Shown
    split: Split
    rule: UncertainCount
    arm: UncertainCount
    better: int = Field(ge=0)
    worse: int = Field(ge=0)
    p: float = Field(ge=0, le=1, allow_inf_nan=False)
    targets: dict[Name, bool]
    kept: bool
    breakdowns: dict[str, dict[str, UncertainCount]]  # the arm's, by kind and language
    requests: dict[ModelName, int]
    tokens: dict[ModelName, int]  # read and written
    prices: dict[Name, _Usd]  # USD per million tokens: input, cached and output
    cost_usd: _Usd
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        _groups_fit(self.split, self.arm.items, self.breakdowns.values())
        return self


class FirstAudioGroup(Model):
    """The recordings of a run of T whose time starts in one place: their items and variants,
    each path's times, and the replies with a search whose progress line began late."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    paths: dict[ReplyPath, PathStats]
    progress_late: int = Field(ge=0)


class FirstAudioLine(Model):
    """One line of `history.jsonl` for a `poe first-audio` run (the module's docstring): its
    agent, whether its tools were left out, its settings and split; its recordings, those cut,
    failed, unanswered and never heard; each path's times, the progress lines and those begun
    late; whether each target held; the numbers by where the time starts; every model's
    requests, the voices' characters, Whisper's billed seconds, the prices and the cost; and the
    clause cache's numbers, when the run had one."""

    kind: Literal["first_audio"] = "first_audio"
    time: datetime
    commit: Commit
    run: Name
    agent: Plain
    tools: bool
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    cut: int = Field(ge=0)
    failures: int = Field(ge=0)
    unanswered: int = Field(ge=0)
    no_audio: int = Field(ge=0)
    paths: dict[ReplyPath, PathStats]
    progress_lines: int = Field(ge=0)
    progress_median_ms: _Ms | None = None
    progress_late: int = Field(ge=0)
    targets: dict[Name, bool | None]
    ends: dict[Name, FirstAudioGroup]  # by where the time starts: `label`, `detector`
    phrase_requests: int = Field(ge=0)
    requests: dict[ModelName, int]
    characters: dict[ModelName, int]
    billed_seconds: float = Field(ge=0, allow_inf_nan=False)  # Whisper's
    price_per_hour_usd: _Usd
    tts_price_per_million_usd: dict[ModelName, _Usd]
    chat_price_per_million_usd: dict[Name, _Usd]  # input, cached and output
    cost_usd: _Usd
    clause_cache: ClauseSummary | None = None
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        _groups_fit(self.split, self.items, [self.ends])
        return self


def _groups_fit(
    split: Split, items: int, strata: Iterable[Mapping[str, UncertainCount | FirstAudioGroup]]
) -> None:
    """ValueError when a group covers more items than the run, or a held-out run's covers fewer
    than `HELD_OUT_MIN_ITEMS`."""
    counts = [group.items for values in strata for group in values.values()]
    if any(count > items for count in counts):
        raise ValueError("a stratum value covers no more items than the run")
    if split == "held-out" and any(count < HELD_OUT_MIN_ITEMS for count in counts):
        raise ValueError(
            f"a held-out run's stratum values each cover at least {HELD_OUT_MIN_ITEMS} items"
        )
