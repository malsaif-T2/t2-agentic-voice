"""What run K0 produces (Q20; plan 006's registration, K0): each answerable dev variant's record,
the numbers at each k from 1 to `DEPTH`, the kept k, the scorecard, and its history line.

A variant's record (`DepthRecord`) holds the passages its raw words' search found, best first,
at most `DEPTH`; the point of the knowledge set each one is (None for a passage `points.toml`
does not hold, which counts as a miss, kb_points.py); and each one's characters as the talker
reads it, the library's knowledge tool's text, cut near `PASSAGE_CHARS`. A variant whose search
failed or passed its limit (`failure`) is counted apart and left out of every number.

At each k (`DepthAt`), over the answerable items, each weighing its variants' share once, as the
item is the unit (run K's `item_rate`): `hit`, the share with an expected point in the top k;
`found`, the share of the item's expected points in the top k; and over the variants, the
characters the talker would read, the top k passages' together (median, 90th percentile, most),
each passage's counted as the library's knowledge tool hands it over (`talker_chars`).
The keep rule (`kept_k`): the smallest k whose `found` is within `MARGIN` of k = `DEPTH`'s,
reckoned in exact fractions, so a share on the margin is kept; a run that did not finish keeps
none. K0 sends no chat request, so its line holds no price and no cost.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from fractions import Fraction
from functools import partial
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from t2_agentic_voice import CallContext, Caller, ToolResult, knowledge_tool
from t2_agentic_voice.ports import Passage

from ole5_voice.evals.knowledge_set import PointId, SpokenLanguage
from ole5_voice.evals.models import Commit, Model, Name, Sha256
from ole5_voice.evals.runs import SCORECARD_FILE, Note, Shown
from ole5_voice.evals.scorecard import quantile
from ole5_voice.evals.talker_measure import CALLER

# The registration's K0: the passages each search reads, k from 1 to this; about the most of a
# passage's text the talker reads; and how far below k = `DEPTH`'s share of expected points
# found the kept k's may be.
DEPTH: Final = 8
PASSAGE_CHARS: Final = 1500
MARGIN: Final = Fraction(1, 20)
# Why a variant has no result: its search failed, or passed its limit.
Failure = Literal["provider", "stuck"]
# Why a run stopped before its end: its smoke search failed, an interrupt, or an error it does
# not score (logged by its type, then raised).
Stopped = Literal["smoke_failed", "interrupted", "error"]
# The call a count of the talker's characters is made in: made up, as the reference search's.
_CONTEXT: Final = CallContext(caller=CALLER, call_id="knowledge-depth", language="ar-SA")
_Share = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
_Chars = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class DepthRecord(Model):
    """One answerable dev variant of K0, searched (the module's docstring)."""

    item: Name
    variant: Name
    language: SpokenLanguage
    expected: tuple[PointId, ...] = Field(min_length=1)
    passages: tuple[str, ...] = Field(default=(), max_length=DEPTH)  # the IDs, best first
    points: tuple[PointId | None, ...] = ()
    chars: tuple[Annotated[int, Field(ge=0)], ...] = ()
    failure: Failure | None = None
    seconds: float = Field(default=0.0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _one_each(self) -> Self:
        if not len(self.passages) == len(self.points) == len(self.chars):
            raise ValueError("a record has a point and characters for each passage found")
        if self.failure is not None and self.passages:
            raise ValueError("a failed search found no passage")
        return self

    def hit(self, k: int) -> Fraction:
        """1 when an expected point is among the first `k` passages, else 0."""
        return Fraction(any(point in self.expected for point in self.points[:k]))

    def found(self, k: int) -> Fraction:
        """The share of the expected points among the first `k` passages."""
        expected = set(self.expected)
        return Fraction(len(expected & set(self.points[:k])), len(expected))

    def read(self, k: int) -> int:
        """The characters the talker would read of the first `k` passages."""
        return sum(self.chars[:k])


class DepthAt(Model):
    """The numbers at one k (the module's docstring); None where no variant was scored."""

    k: int = Field(ge=1, le=DEPTH)
    hit: _Share | None
    found: _Share | None
    chars_median: _Chars | None
    chars_p90: _Chars | None
    chars_most: int | None = Field(ge=0)


class DepthRun(Model):
    """What a run of K0 was: when, at which commit, with which settings and data, and why."""

    name: Name
    started_at: datetime
    commit: Commit
    split: Literal["dev"] = "dev"  # held-out is never read by K0
    settings: Shown
    data_digest: Sha256
    note: Note


class DepthScorecard(Model):
    """A run of K0's scorecard: its records, the items and variants scored, the failures, the
    numbers at each k and the kept k."""

    run: DepthRun
    complete: bool
    stopped: Stopped | None
    items: int = Field(ge=0)
    variants: int = Field(ge=0)  # every search the run sent, a failed one's included
    failures: int = Field(ge=0)
    depths: tuple[DepthAt, ...]
    kept_k: int | None = Field(ge=1, le=DEPTH)
    records: tuple[DepthRecord, ...] = ()


class DepthLine(Model):
    """One line of `history.jsonl` for a `poe knowledge-depth` run (run K0): its settings, the
    items and variants it scored, its failures, the numbers at each k, the kept k and why it
    stopped. Its searches go to the knowledge base alone: no chat request, so no cost."""

    kind: Literal["knowledge_depth"] = "knowledge_depth"
    time: datetime
    commit: Commit
    run: Name
    settings: Shown
    split: Literal["dev"] = "dev"
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    failures: int = Field(ge=0)
    depths: tuple[DepthAt, ...]
    kept_k: int | None = Field(ge=1, le=DEPTH)
    stopped: Stopped | None
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool


class _ReadPassage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    text: str


class _Read(BaseModel):
    """What the knowledge tool hands the talker, as K0 reads it: each passage's text."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    passages: tuple[_ReadPassage, ...]


class _Given:
    """A knowledge base that gives back the passages one search found (a `KnowledgeBase`)."""

    def __init__(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)

    async def search(
        self, query: str, *, language: str, caller: Caller, limit: int
    ) -> list[Passage]:
        return self._passages[:limit]


async def talker_chars(passages: Sequence[Passage]) -> tuple[int, ...]:
    """Each of `passages`' characters as the talker reads it: its text as the library's
    knowledge tool hands it over, cut near `PASSAGE_CHARS` (the tool's `passage_chars`)."""
    tool = knowledge_tool(
        _Given(passages),
        description="Run K0's count of what the talker reads.",
        limit=DEPTH,
        passage_chars=PASSAGE_CHARS,
    )
    result: ToolResult = await tool.function(_CONTEXT, query="knowledge depth")
    return tuple(len(passage.text) for passage in _Read.model_validate(result.data).passages)


def by_item(
    records: Sequence[DepthRecord], value: Callable[[DepthRecord], Fraction]
) -> Fraction | None:
    """`value` averaged over each item's scored variants, then over the items; None when no
    variant was scored."""
    shares: dict[str, list[Fraction]] = defaultdict(list)
    for record in records:
        if record.failure is None:
            shares[record.item].append(value(record))
    if not shares:
        return None
    means = [sum(found, Fraction(0)) / len(found) for found in shares.values()]
    return sum(means, Fraction(0)) / len(means)


def kept_k(records: Sequence[DepthRecord]) -> int | None:
    """The smallest k whose share of expected points found is within `MARGIN` of k =
    `DEPTH`'s; None when no variant was scored."""
    found = [by_item(records, partial(DepthRecord.found, k=k)) for k in range(1, DEPTH + 1)]
    deepest = found[-1]
    if deepest is None:
        return None
    # Every share is over the same scored variants, and k = DEPTH's is within the margin.
    return next(
        k
        for k, share in enumerate(found, start=1)
        if share is not None and share + MARGIN >= deepest
    )


def depth_at(records: Sequence[DepthRecord], k: int) -> DepthAt:
    """The numbers at `k` over `records` (the module's docstring)."""
    hit = by_item(records, lambda record: record.hit(k))
    found = by_item(records, lambda record: record.found(k))
    read = sorted(float(record.read(k)) for record in records if record.failure is None)
    return DepthAt(
        k=k,
        hit=None if hit is None else float(hit),
        found=None if found is None else float(found),
        chars_median=quantile(read, 0.5),
        chars_p90=quantile(read, 0.9),
        chars_most=int(read[-1]) if read else None,
    )


def scorecard(
    run: DepthRun, records: Sequence[DepthRecord], *, complete: bool, stopped: Stopped | None
) -> DepthScorecard:
    """The scorecard of `records`; the kept k only when the run is `complete`."""
    scored = [record for record in records if record.failure is None]
    return DepthScorecard(
        run=run,
        complete=complete,
        stopped=stopped,
        items=len({record.item for record in scored}),
        variants=len(records),
        failures=len(records) - len(scored),
        depths=tuple(depth_at(records, k) for k in range(1, DEPTH + 1)),
        kept_k=kept_k(records) if complete else None,
        records=tuple(records),
    )


def depth_line(card: DepthScorecard) -> DepthLine:
    """The history line of a run of K0's scorecard."""
    run = card.run
    return DepthLine(
        time=run.started_at,
        commit=run.commit,
        run=run.name,
        settings=run.settings,
        items=card.items,
        variants=card.variants,
        failures=card.failures,
        depths=card.depths,
        kept_k=card.kept_k,
        stopped=card.stopped,
        scorecard=SCORECARD_FILE,
        data_digest=run.data_digest,
        note=run.note,
        complete=card.complete,
    )
