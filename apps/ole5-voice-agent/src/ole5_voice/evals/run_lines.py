"""The history lines of the run kinds beside `poe eval`'s (plan 003): an end-of-turn run of
`poe eot` (`EotLine`), a timing run of `poe eval-timing` (`TimingLine`) and an overlap run of
`poe overlap` (`OverlapLine`, plan 005), each marked by its `kind`, and `AnyLine`, the one shape
every line of `history.jsonl` is read as, a line with no `kind` being `poe eval`'s
(`runs.HistoryLine`, whose lines predate the field). Strict as every history line: a held-out
run's breakdowns hold no group of fewer than `HELD_OUT_MIN_ITEMS` items, and a secret setting is
shown only as set or not set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Discriminator, Field, Tag, model_validator

from ole5_voice.evals.models import Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, HistoryLine, Note, Plain, Shown

# A model's name as a history line keys its numbers by it (`whisper-large-v3`,
# `canopylabs/orpheus-arabic-saudi`).
ModelName = Annotated[Plain, Field(min_length=1, max_length=128)]
_Ms = Annotated[float, Field(allow_inf_nan=False)]
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class EotCount(Model):
    """One stratum value of an end-of-turn run: its items and variants, and how many were cut
    off and missed."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    cut_offs: int = Field(ge=0)
    misses: int = Field(ge=0)


class EotLine(Model):
    """One line of `history.jsonl` for a `poe eot` run of the pipeline (plan 003's registration,
    E): the paused requests' cut-offs, misses and delay, by stratum value; the secondary set's,
    when it ran. It spends nothing."""

    kind: Literal["eot"] = "eot"
    time: datetime
    commit: Commit
    run: Name
    answerer: Name
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    cut_offs: int = Field(ge=0)
    misses: int = Field(ge=0)
    delay_median_ms: _Ms | None
    delay_p90_ms: _Ms | None
    secondary: EotCount | None = None
    breakdowns: dict[str, dict[str, EotCount]]  # the paused requests', by language and device
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        counts = [value.items for values in self.breakdowns.values() for value in values.values()]
        if any(items > self.items for items in counts):
            raise ValueError("a stratum value covers no more items than the run")
        if self.split == "held-out" and any(items < HELD_OUT_MIN_ITEMS for items in counts):
            raise ValueError(
                f"a held-out run's stratum values each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        return self


class TimingLine(Model):
    """One line of `history.jsonl` for a `poe eval-timing` run (plan 003's registration, T):
    its variants, those cut into two turns or more and those that failed; each model's requests
    and characters, Whisper's billed seconds, the prices and the cost, every request the run
    sent counted (its smoke test's and a retried variant's included, and the fixed phrases'
    that the phrase cache sent before the first variant, `phrase_requests`); and each step's
    median over the timed turns, in ms."""

    kind: Literal["timing"] = "timing"
    time: datetime
    commit: Commit
    run: Name
    settings: Shown
    split: Split
    variants: int = Field(ge=0)
    cut_variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    phrase_requests: int = Field(ge=0)
    requests: dict[ModelName, int]
    characters: dict[ModelName, int]
    billed_seconds: float = Field(ge=0, allow_inf_nan=False)  # Whisper's
    price_per_hour_usd: _Usd  # Whisper's, an hour of billed audio
    tts_price_per_million_usd: dict[ModelName, _Usd]  # each Orpheus model's, per million chars
    cost_usd: _Usd
    medians_ms: dict[Name, _Ms | None]
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool


class OverlapCount(Model):
    """One stratum value of an overlap run: its items and variants, those right, those that
    should stop and did, and those that should go on and stopped."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    right: int = Field(ge=0)
    should_stop: int = Field(ge=0)
    stopped: int = Field(ge=0)
    should_go_on: int = Field(ge=0)
    false_stops: int = Field(ge=0)


class OverlapLine(Model):
    """One line of `history.jsonl` for a `poe overlap` run of the replay (plan 005's
    registration, the arm O): its variants and those right, the stop words' stop time from the
    owner's mark (median and 90th percentile), the most requests that decided an overlap,
    whether each target held (None when nothing gave it), the numbers by stratum value, and its
    spend: every Whisper request it sent, their billed seconds, the price and the cost."""

    kind: Literal["overlap"] = "overlap"
    time: datetime
    commit: Commit
    run: Name
    answerer: Name
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    right: int = Field(ge=0)
    stop_median_ms: _Ms | None
    stop_p90_ms: _Ms | None
    requests_max: int | None = Field(ge=0)
    targets: dict[Name, bool | None]
    breakdowns: dict[str, dict[str, OverlapCount]]  # by kind, language and device
    requests: int = Field(ge=0)
    billed_seconds: float = Field(ge=0, allow_inf_nan=False)
    price_per_hour_usd: _Usd
    cost_usd: _Usd
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool

    @model_validator(mode="after")
    def _held_out_groups(self) -> Self:
        counts = [value.items for values in self.breakdowns.values() for value in values.values()]
        if any(items > self.items for items in counts):
            raise ValueError("a stratum value covers no more items than the run")
        if self.split == "held-out" and any(items < HELD_OUT_MIN_ITEMS for items in counts):
            raise ValueError(
                f"a held-out run's stratum values each cover at least {HELD_OUT_MIN_ITEMS} items"
            )
        return self


def _kind(value: object) -> str:
    """A line's kind: its `kind` field, or `stt` for `poe eval`'s, which has none."""
    found = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return found if isinstance(found, str) else "stt"


# Every line of `history.jsonl`, by its kind.
AnyLine = Annotated[
    Annotated[HistoryLine, Tag("stt")]
    | Annotated[EotLine, Tag("eot")]
    | Annotated[TimingLine, Tag("timing")]
    | Annotated[OverlapLine, Tag("overlap")],
    Discriminator(_kind),
]
