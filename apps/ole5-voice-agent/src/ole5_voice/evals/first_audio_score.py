"""The scorer of `poe first-audio` (plan 006's registration, T, the time to first audio): what a
replayed call gives (`ReplayedTurn`, `ReplayedCall`), each recording's result, the numbers by
path (a reply with a search, and with none), the registered targets, and what the run spent.

**A turn's time** is its call report's time to first audio: from the end of the caller's speech
(the recording's label where the owner marked one, else the speech detector's stop less its
delay, reported apart as `detector`) to the first audible frame of the reply sent; and, where a
progress line played, to its first audible frame. **The timed turn** is a call's one answered
turn; a call that answered more than one (the caller's turn cut in two) is `cut`, reported apart
and left out of the numbers, as is one that failed or answered nothing. **A reply never heard**,
a timed turn whose reply sent no audio before the call ended (`no_audio`), took longer than the
call's tail (first_audio_run.py's `tail_of`, the slowest reply that still answers): it stays in
its path's turns, ranked after every reply heard, so a quantile that reaches it has no value, and
its target fails when the tail's time, the least such a reply took, would break the bound, and is
unknown (`holds` None) otherwise. **The path** of a reply is `search` when a tool ran in it, else
`no_search`. Quantiles are type 7 (`scorecard.quantile`).

**The targets** (the registration's, Q7): a reply with no search at a median of at most
1,600 ms and a 90th percentile of at most 2,400 ms; with a search, at most 3,000 and 4,000 ms,
and a progress line begun by 2,000 ms whenever the reply had not begun by then. A held-out run's
numbers are aggregates only: a target over fewer than `HELD_OUT_MIN_ITEMS` items is withheld.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioChunk

from ole5_voice.evals.models import Device, Language, Model, Name, Split
from ole5_voice.evals.overlap_score import Target
from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS
from ole5_voice.evals.scorecard import quantile

PROGRESS_BY_MS: Final = 2000.0
ReplyPath = Literal["search", "no_search"]
# The registration's bounds, by target: its path, its quantile and its most ms.
BOUNDS: Final[tuple[tuple[str, ReplyPath, float, float], ...]] = (
    ("no_search_median_ms", "no_search", 0.5, 1600.0),
    ("no_search_p90_ms", "no_search", 0.9, 2400.0),
    ("search_median_ms", "search", 0.5, 3000.0),
    ("search_p90_ms", "search", 0.9, 4000.0),
)
# Where a turn's time starts: the owner's label of the speech's end, or the detector's stop.
EndSource = Literal["label", "detector"]
_Ms = Annotated[float, Field(ge=0, allow_inf_nan=False)]
# A reply's opening as a run keeps it: a file of its folder's `replies/`, named by its recording
# and reply (first_audio_run.py), so a scorecard read back names no file outside it.
Opening = Annotated[str, StringConstraints(pattern=r"^replies/[a-z0-9][a-z0-9_.-]{0,127}\.wav$")]


class ReplayedTurn(Model):
    """One answered turn of a replayed call, as its call report gives it: the time to the
    reply's first audible frame, whether a tool ran in the reply, the time to its progress
    line's first audible frame where one played, and the failure it met (a `ProviderError`
    kind)."""

    ttfa_ms: _Ms | None = None
    searched: bool = False
    progress_ms: _Ms | None = None
    failure: Name | None = None


class ChatSpend(Model):
    """What a call's chat model requests used, and the headroom for the key's day its provider
    last reported (None: none)."""

    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    remaining_requests: int | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class ReplayedCall:
    """One recording's call: each answered turn in order, each one's reply's opening audio as
    sent (for the owner's listen; None where none came), and what the call used: the speech
    models' usage as its report counts it, and the chat model's."""

    turns: tuple[ReplayedTurn, ...]
    openings: tuple[AudioChunk | None, ...]
    usage: tuple[ModelUsage, ...]
    chat: ChatSpend


class AudioResult(Model):
    """One recording of a run: its strata, where its time starts and the label's time, how many
    calls it took (a rate-limited one is run again), its last call's turns, whether it was cut,
    its timed turn, each reply's opening as a file of the run's folder, and its failure."""

    item: Name
    variant: Name
    split: Split
    language: Language
    device: Device
    end: EndSource
    end_ms: float | None = None
    attempts: int = Field(default=1, ge=1)
    turns: tuple[ReplayedTurn, ...] = ()
    cut: bool = False
    timed: ReplayedTurn | None = None
    openings: tuple[Opening | None, ...] = ()
    failure: str | None = None


def result_of(
    base: dict[str, object], call: ReplayedCall, attempts: int, openings: tuple[str | None, ...]
) -> AudioResult:
    """A recording's result from its last call: `base` its strata and end."""
    failure = next((t.failure for t in call.turns if t.failure is not None), None)
    cut = len(call.turns) > 1
    timed = call.turns[0] if len(call.turns) == 1 and failure is None else None
    found = {"attempts": attempts, "turns": call.turns, "cut": cut, "timed": timed}
    return AudioResult.model_validate(base | found | {"openings": openings, "failure": failure})


class PathStats(Model):
    """One path's timed turns, those whose reply was never heard, their median and 90th
    percentile (None where one reaches a reply never heard), and their items."""

    turns: int = Field(ge=0)
    items: int = Field(ge=0)
    no_audio: int = Field(default=0, ge=0)
    median_ms: float | None = None
    p90_ms: float | None = None


class AudioMetrics(Model):
    """The numbers of some recordings: how many, their items, those cut, failed or unanswered,
    the timed replies never heard, each path's times, the progress lines played and their
    median, and the replies with a search that had not begun by `PROGRESS_BY_MS` and no
    progress line begun by then."""

    variants: int = Field(ge=0)
    items: int = Field(ge=0)
    cut: int = Field(ge=0)
    failures: int = Field(ge=0)
    unanswered: int = Field(ge=0)
    no_audio: int = Field(default=0, ge=0)
    paths: dict[ReplyPath, PathStats]
    progress_lines: int = Field(ge=0)
    progress_median_ms: float | None = None
    progress_late: int = Field(ge=0)


def _path(turn: ReplayedTurn) -> ReplyPath:
    return "search" if turn.searched else "no_search"


def _times(results: Sequence[AudioResult], path: ReplyPath) -> tuple[list[float], int]:
    """The times of `path`'s timed replies heard, sorted, and how many were never heard."""
    timed = [t for r in results if (t := r.timed) is not None and _path(t) == path]
    heard = sorted(t.ttfa_ms for t in timed if t.ttfa_ms is not None)
    return heard, len(timed) - len(heard)


def heard_quantile(heard: Sequence[float], unheard: int, q: float) -> float | None:
    """The `q` quantile (type 7) of `heard` (sorted) and `unheard` replies ranked after every
    one of them; None when there is none, or when it reaches an unheard one."""
    if not heard:
        return None
    position = q * (len(heard) + unheard - 1)
    low = math.floor(position)
    high = low if position == low else low + 1
    if high >= len(heard):
        return None
    return heard[low] + (heard[high] - heard[low]) * (position - low)


def metrics(results: Sequence[AudioResult]) -> AudioMetrics:
    """The numbers of `results` (the module's docstring)."""
    timed = [(r, t) for r in results if (t := r.timed) is not None]
    paths: dict[ReplyPath, PathStats] = {}
    for path in ("search", "no_search"):
        heard, unheard = _times(results, path)
        paths[path] = PathStats(
            turns=len(heard) + unheard,
            items=len({r.item for r, t in timed if _path(t) == path}),
            no_audio=unheard,
            median_ms=heard_quantile(heard, unheard, 0.5),
            p90_ms=heard_quantile(heard, unheard, 0.9),
        )
    progress = sorted(p for _, t in timed if (p := t.progress_ms) is not None)
    late = [
        t
        for _, t in timed
        if t.searched
        and (t.ttfa_ms is None or t.ttfa_ms > PROGRESS_BY_MS)
        and (t.progress_ms is None or t.progress_ms > PROGRESS_BY_MS)
    ]
    return AudioMetrics(
        variants=len(results),
        items=len({r.item for r in results}),
        cut=sum(r.cut for r in results),
        failures=sum(r.failure is not None for r in results),
        unanswered=sum(not r.turns and r.failure is None for r in results),
        no_audio=sum(t.ttfa_ms is None for _, t in timed),
        paths=paths,
        progress_lines=len(progress),
        progress_median_ms=quantile(progress, 0.5),
        progress_late=len(late),
    )


def targets(results: Sequence[AudioResult], *, held_out: bool, tail_s: float) -> tuple[Target, ...]:
    """The registration's targets on `results`, whose calls had `tail_s` of silence after each
    recording; one over too few items in a held-out run, or over none, withheld, and one whose
    quantile reaches a reply never heard failed or unknown (the module's docstring)."""
    found = metrics(results)
    rows: list[tuple[str, int, float | None, float, bool | None]] = []
    for name, path, q, bound in BOUNDS:
        stats = found.paths[path]
        value = stats.median_ms if q == 0.5 else stats.p90_ms
        holds = None if value is None else value <= bound
        heard, unheard = _times(results, path)
        if value is None and unheard:  # at least the tail, for each never heard
            least = quantile(sorted([*heard, *[tail_s * 1000.0] * unheard]), q)
            holds = False if least is not None and least > bound else None
        rows.append((name, stats.items, value, bound, holds))
    late = float(found.progress_late)
    rows.append(("progress_late", found.paths["search"].items, late, 0.0, late <= 0.0))
    shown = []
    for name, items, value, bound, holds in rows:
        if items == 0 or (held_out and items < HELD_OUT_MIN_ITEMS):
            value, holds = None, None
        shown.append(
            Target(name=name, items=items, value=value, bound=bound, at_most=True, holds=holds)
        )
    return tuple(shown)


_STRATA: Final[dict[str, Callable[[AudioResult], str]]] = {
    "end": lambda result: result.end,
    "language": lambda result: result.language,
}


def breakdowns(results: Iterable[AudioResult]) -> dict[str, dict[str, AudioMetrics]]:
    """A dev run's numbers by where the time starts and by language."""
    found: dict[str, dict[str, AudioMetrics]] = {}
    for stratum, key in _STRATA.items():
        groups: dict[str, list[AudioResult]] = defaultdict(list)
        for result in results:
            groups[key(result)].append(result)
        found[stratum] = {value: metrics(group) for value, group in sorted(groups.items())}
    return found
