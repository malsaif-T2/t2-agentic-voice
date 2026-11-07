"""What run K produces (plan 006's registration, K): each variant's record, the numbers of a run
or of a group of its variants, the registered targets, and the scorecard.

A variant is keyed by its item and its place in the item (`v1`, `v2`, ...), since variants have
no ID. Its record holds what the call did, the talker's searches and the reference search of its
raw words, and what is read from them: retrieval (an expected point in the top 5) from the
talker's first query and from the raw words, for an answerable item; a search made exactly when
needed; the reply language; the judge's verdict, and whether it is the item kind's passing one
(`judge.PASSING`). The time to the first clause is kept twice: on the wall clock, and the model's
own, the time its tools ran before it taken out (`HeardTurn.own_first_clause_s`, Q15), which the
keep rule reads (`KEEP_TIME`). A variant with no result to score (`failure`: the provider's, its
limit passed, or the judge's) is counted apart and left out of every rate.

A rate is kept over the variants (`rate`) and over the items (`item_rate`, each item weighing
its variants' share once, as the item is the unit): the targets on items read `item_rate`, the
reply language's target on variants reads `rate`. A held-out run's scorecard holds aggregates
only: no variant, every group of fewer than `HELD_OUT_MIN_ITEMS` answered items pooled as
`other` (itself left out when as small), and within a group shown, and in the totals, each rate
and median taken over fewer items left out. Built with the constructor or `model_validate`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from ole5_voice.evals.judge import Judged
from ole5_voice.evals.knowledge_set import KnowledgeKind, SpokenLanguage
from ole5_voice.evals.models import OTHER, Commit, Model, Name, Sha256, Split
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Note, Plain, Shown
from ole5_voice.evals.scorecard import quantile
from ole5_voice.evals.talker_data import VERDICTS, Failure, HeardTurn, ModelName, ModelSpend, Tag

# Why a run stopped before its end: its smoke test failed, the cap, the key's daily limit, an
# interrupt, or an error it does not score (logged by its type, then raised).
Stopped = Literal["smoke_failed", "cap", "daily_limit", "interrupted", "error"]
# The registered targets (the registration's "The targets"): each a share at least this high.
TARGETS: Final[Mapping[str, float]] = {
    "retrieval": 0.90,
    "answers": 0.80,
    "honest": 0.90,
    "language": 0.95,
}
# The time run K's keep rule reads (Q15): the model's own time to the first clause, the tools'
# time taken out, at the median; the wall clock's, the search in it, is reported beside it.
KEEP_TIME: Final = "own_first_clause_median_s"
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
_S = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class SearchMade(Model):
    """One search the talker made: its query, and the first five passages' IDs."""

    query: str
    passages: tuple[str, ...] = ()
    failed: bool = False


class VariantRecord(Model):
    """One variant of run K, scored (the module's docstring)."""

    item: Name
    variant: Name
    split: Split
    kind: KnowledgeKind
    language: SpokenLanguage
    needs_search: bool
    tag: Tag  # the language its reply is held to
    turn: HeardTurn | None = None
    violations: int = Field(default=0, ge=0)
    searches: tuple[SearchMade, ...] = ()
    raw_passages: tuple[str, ...] | None = None  # the reference search's, an answerable item's
    own_hit: bool | None = None
    raw_hit: bool | None = None
    search_right: bool | None = None
    language_right: bool | None = None
    judged: Judged | None = None
    passed: bool | None = None
    failure: Failure | None = None
    seconds: _S = 0.0

    @model_validator(mode="after")
    def _scored_once_answered(self) -> Self:
        if (self.failure is None) != (self.passed is not None):
            raise ValueError("a variant has a verdict exactly when nothing failed")
        return self


class Rate(Model):
    """A share: `hits` of `of` variants, of `items` items; over the variants and over the
    items."""

    hits: int = Field(ge=0)
    of: int = Field(ge=0)
    items: int = Field(ge=0)
    rate: float | None
    item_rate: float | None


class TalkerMetrics(Model):
    """The numbers of a run, or of a group of its variants; None where nothing counts, or where
    a held-out group's count of items is too small to show."""

    items: int = Field(ge=0)  # the items of its answered variants
    variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    verdicts: dict[str, int]
    answers: Rate | None  # answerable variants judged right
    honest: Rate | None  # `none` variants answered with an honest "not in my knowledge"
    passed: Rate | None  # every kind's passing verdict
    retrieval: Rate | None  # an expected point in the top 5, from the talker's own query
    retrieval_raw: Rate | None  # the same from the variant's raw words, the reference
    search: Rate | None  # a search made exactly when needed
    language: Rate | None  # the reply in the caller's language
    words_median: float | None
    words_p90: float | None
    first_clause_median_s: float | None  # on the wall clock, the tools' time in it
    first_clause_p90_s: float | None
    own_first_clause_median_s: float | None = None  # the model's own (Q15): no tool's time
    own_first_clause_p90_s: float | None = None
    first_token_median_s: float | None
    blocked: int = Field(ge=0)
    violations: int = Field(ge=0)
    model_requests: int = Field(ge=0)


class PriceShown(Model):
    """A model's price, as the command line gave it: USD per million tokens."""

    input_usd: _Usd
    output_usd: _Usd


class TalkerRun(Model):
    """What a run of K was: its arm and model, the judge's model, its split, settings, prices,
    cap and data, and why it was made."""

    name: Name
    started_at: datetime
    commit: Commit
    arm: Name
    model: Plain
    judge_model: Plain
    split: Split
    settings: Shown
    prices: dict[ModelName, PriceShown]
    cap_usd: _Usd
    data_digest: Sha256
    note: Note
    smoke_only: bool = False


class Session(Model):
    """One session of a run (a run stopped at the daily limit goes on in another): when it
    began, why it stopped, the variants it finished and what it spent."""

    started_at: datetime
    stopped: Stopped | None
    variants: int = Field(ge=0)
    spend: tuple[ModelSpend, ...] = ()
    cost_usd: _Usd = 0.0


class TalkerScorecard(Model):
    """Run K's scorecard (the module's docstring), checked as it is read; `keep_time` names the
    time the keep rule reads (talker_keep.py)."""

    run: TalkerRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    keep_time: Literal["own_first_clause_median_s"] = KEEP_TIME
    complete: bool
    stopped: Stopped | None
    sessions: tuple[Session, ...]
    totals: TalkerMetrics
    breakdowns: dict[str, dict[str, TalkerMetrics]]  # by language and by kind
    targets: dict[str, bool | None]
    cost_usd: _Usd
    variants: tuple[VariantRecord, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        held_out = self.run.split == "held-out"
        if held_out and self.variants:
            raise ValueError("a held-out run's scorecard holds aggregates only")
        groups = [m.items for values in self.breakdowns.values() for m in values.values()]
        if held_out and any(items < HELD_OUT_MIN_ITEMS for items in groups):
            raise ValueError(f"a held-out run's groups each cover {HELD_OUT_MIN_ITEMS} items")
        if any(record.split != self.run.split for record in self.variants):
            raise ValueError("a scorecard holds only its own split's variants")
        keys = [(record.item, record.variant) for record in self.variants]
        if len(set(keys)) != len(keys):
            raise ValueError("a scorecard scores each variant once")
        return self


def rate(
    records: Sequence[VariantRecord], value: Callable[[VariantRecord], bool | None], least: int
) -> Rate | None:
    """The share of `records` (answered ones) for which `value` is true, among those it
    counts (not None); None when it counts none, or covers fewer than `least` items."""
    counted = [(record.item, hit) for record in records if (hit := value(record)) is not None]
    by_item: dict[str, list[bool]] = defaultdict(list)
    for item, hit in counted:
        by_item[item].append(hit)
    if not counted or len(by_item) < least:
        return None
    hits = sum(hit for _, hit in counted)
    shares = [sum(found) / len(found) for found in by_item.values()]
    return Rate(
        hits=hits,
        of=len(counted),
        items=len(by_item),
        rate=hits / len(counted),
        item_rate=sum(shares) / len(shares),
    )


def metrics(records: Sequence[VariantRecord], *, least: int = 1) -> TalkerMetrics:
    """The numbers of `records`; a rate or a median over fewer than `least` items left out."""
    answered = [r for r in records if r.failure is None]
    turns = [r.turn for r in answered if r.turn is not None]
    shown = len({r.item for r in answered}) >= least

    def spread(values: Iterable[float | None]) -> tuple[float | None, float | None]:
        ordered = sorted(v for v in values if v is not None) if shown else []
        return quantile(ordered, 0.5), quantile(ordered, 0.9)

    words = spread(float(turn.words) for turn in turns)
    first = spread(turn.first_clause_s for turn in turns)
    own = spread(turn.own_first_clause_s for turn in turns)
    verdicts = Counter(r.judged.verdict for r in answered if r.judged and r.judged.verdict)
    return TalkerMetrics(
        items=len({r.item for r in answered}),
        variants=len(records),
        failures=len(records) - len(answered),
        verdicts={verdict: verdicts[verdict] for verdict in VERDICTS},
        answers=rate(answered, lambda r: r.passed if r.kind == "answerable" else None, least),
        honest=rate(answered, lambda r: r.passed if r.kind == "none" else None, least),
        passed=rate(answered, lambda r: r.passed, least),
        retrieval=rate(answered, lambda r: r.own_hit, least),
        retrieval_raw=rate(answered, lambda r: r.raw_hit, least),
        search=rate(answered, lambda r: r.search_right, least),
        language=rate(answered, lambda r: r.language_right, least),
        words_median=words[0],
        words_p90=words[1],
        first_clause_median_s=first[0],
        first_clause_p90_s=first[1],
        own_first_clause_median_s=own[0],
        own_first_clause_p90_s=own[1],
        first_token_median_s=spread(turn.first_token_s for turn in turns)[0],
        blocked=sum(turn.blocked for turn in turns),
        violations=sum(r.violations for r in records),  # every call's: a hard constraint
        model_requests=sum(turn.model_requests for turn in turns),
    )


def targets(totals: TalkerMetrics) -> dict[str, bool | None]:
    """Whether each registered target held; None when nothing gave it."""
    shares = {
        "retrieval": totals.retrieval.item_rate if totals.retrieval else None,
        "answers": totals.answers.item_rate if totals.answers else None,
        "honest": totals.honest.item_rate if totals.honest else None,
        "language": totals.language.rate if totals.language else None,
    }
    held: dict[str, bool | None] = {
        name: None if share is None else share >= TARGETS[name] for name, share in shares.items()
    }
    return held | {"guard": totals.violations == 0 if totals.variants else None}


_STRATA: Final[Mapping[str, Callable[[VariantRecord], str]]] = {
    "language": lambda record: record.language,
    "kind": lambda record: record.kind,
}


def breakdowns(
    records: Sequence[VariantRecord], *, held_out: bool
) -> dict[str, dict[str, TalkerMetrics]]:
    """The numbers by language and by kind; a held-out run's small groups pooled."""
    least = HELD_OUT_MIN_ITEMS if held_out else 1
    found: dict[str, dict[str, TalkerMetrics]] = {}
    for stratum, key in _STRATA.items():
        groups: dict[str, list[VariantRecord]] = defaultdict(list)
        for record in records:
            groups[key(record)].append(record)
        if held_out:
            groups = _pooled(groups)
        found[stratum] = {v: metrics(g, least=least) for v, g in sorted(groups.items())}
    return found


def _pooled(groups: dict[str, list[VariantRecord]]) -> dict[str, list[VariantRecord]]:
    """Each group of `HELD_OUT_MIN_ITEMS` answered items or more, the others pooled as `other`,
    left out when it too covers fewer."""
    kept = {value: group for value, group in groups.items() if _items(group) >= HELD_OUT_MIN_ITEMS}
    small = [record for value, group in groups.items() if value not in kept for record in group]
    if _items(small) >= HELD_OUT_MIN_ITEMS:
        kept[OTHER] = small
    return kept


def _items(records: Iterable[VariantRecord]) -> int:
    return len({record.item for record in records if record.failure is None})


def scorecard(
    run: TalkerRun,
    records: Sequence[VariantRecord],
    *,
    complete: bool,
    stopped: Stopped | None,
    sessions: Sequence[Session],
) -> TalkerScorecard:
    """The scorecard of `records`; a held-out run's aggregates only."""
    held_out = run.split == "held-out"
    totals = metrics(records, least=HELD_OUT_MIN_ITEMS if held_out else 1)
    return TalkerScorecard(
        run=run,
        complete=complete,
        stopped=stopped,
        sessions=tuple(sessions),
        totals=totals,
        breakdowns=breakdowns(records, held_out=held_out),
        targets=targets(totals),
        cost_usd=sum(session.cost_usd for session in sessions),
        variants=() if held_out else tuple(records),
    )
