"""What the clause cache counts (adapters/clause_cache.py): `ClauseCounts`, public through the
`stores` facade, which a timing run reads for each call (plan 007's run I), and the tally that
grows until the counts are taken. No text and no key is ever counted.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The look-ups' seconds kept between two takings of the counts, the latest (a runtime that
# never takes them keeps no more).
TIMES_KEPT = 10_000
# Why a take was not kept: it raised, was stopped, came back cut short, gave no audio, came at
# two rates, was past the largest file read, found the writer's queue full, was held already, or
# came while the cache was not open.
NotKept = Literal[
    "failed",
    "stopped",
    "cut_short",
    "no_audio",
    "sample_rates",
    "too_large",
    "queue_full",
    "held",
    "closed",
]


class ClauseCounts(BaseModel):
    """What the clause cache did since it opened or its counts were last taken: its hits and
    misses, the takes kept and those not kept by why, the files that were no take, the writes
    that failed, the entries the bound removed, the entries and megabytes it holds now, and each
    look-up's seconds, hits' and misses' apart."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hits: int = 0
    misses: int = 0
    kept: int = 0
    not_kept: dict[NotKept, int] = Field(default_factory=dict)
    unreadable: int = 0
    write_failures: int = 0
    removed: int = 0
    entries: int = 0
    megabytes: float = 0.0
    hit_s: tuple[float, ...] = ()
    miss_s: tuple[float, ...] = ()


def _times() -> deque[float]:
    return deque(maxlen=TIMES_KEPT)


@dataclass
class Tally:
    """The counts as they grow, until taken."""

    hits: int = 0
    misses: int = 0
    kept: int = 0
    unreadable: int = 0
    write_failures: int = 0
    removed: int = 0
    not_kept: dict[NotKept, int] = field(default_factory=dict)
    hit_s: deque[float] = field(default_factory=_times)
    miss_s: deque[float] = field(default_factory=_times)

    def why(self, why: NotKept) -> None:
        """A take not kept, for `why`."""
        self.not_kept[why] = self.not_kept.get(why, 0) + 1

    def looked_up(self, seconds: float, *, hit: bool) -> None:
        """A look-up that took `seconds`, a hit or a miss."""
        if hit:
            self.hits += 1
            self.hit_s.append(seconds)
        else:
            self.misses += 1
            self.miss_s.append(seconds)

    def counts(self, *, entries: int, megabytes: float) -> ClauseCounts:
        """The counts so far, with the `entries` and `megabytes` the cache holds now."""
        return ClauseCounts(
            hits=self.hits,
            misses=self.misses,
            kept=self.kept,
            not_kept=dict(self.not_kept),
            unreadable=self.unreadable,
            write_failures=self.write_failures,
            removed=self.removed,
            entries=entries,
            megabytes=megabytes,
            hit_s=tuple(self.hit_s),
            miss_s=tuple(self.miss_s),
        )
