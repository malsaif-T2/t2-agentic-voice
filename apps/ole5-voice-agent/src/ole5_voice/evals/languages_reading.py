"""Condition 4 of run H's keep rule (plan 007's "Run H"), read across the passes of
`poe eval-languages` (languages_run.py's `--read`; each pass scored by languages_score.py).

`read_passes` reads the passes of one commit, split and data together: against the two off
passes (no classifier), each classifier pass's paused cut-offs, at most the worse off pass's
plus one (D-067's measured noise), and the turn-end delay, the median of the paired differences
(same variant, same turn: a variant whose passes ended a different number of turns is left
unpaired) between the pass and the mean of the two off passes, which may not be both over
`DELAY_BOUND_MS` and over the off passes' own (the median of their paired differences, taken as
a size). Condition 4 holds when both hold.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from ole5_voice.evals.languages_card import LanguageResult, LanguagesScorecard

DELAY_BOUND_MS: Final = 50.0  # condition 4's bound on the median paired turn-end difference


@dataclass(frozen=True)
class Reading:
    """Condition 4 of one classifier pass (the module's docstring): its paused cut-offs and
    the most allowed; the turns paired and the variants left unpaired; the median paired
    turn-end difference against the off passes' mean (`delay_ms`) and the off passes' own
    (`off_ms`); and whether it holds (None when no turn was paired)."""

    run: str
    classifier: str
    cut_offs: int
    allowed: int
    pairs: int
    unpaired: int
    delay_ms: float | None
    off_ms: float | None
    holds: bool | None


Pass = tuple[LanguagesScorecard, Sequence[LanguageResult]]


def read_passes(passes: Sequence[Pass]) -> tuple[Reading, ...]:
    """Condition 4 of each classifier pass of `passes`, in their order, against its two off
    passes; ValueError for passes that are not of one commit, split and data, an incomplete
    one, or not exactly two off passes."""
    cards = [card for card, _ in passes]
    for field, says in (
        ("commit", "one commit"),
        ("split", "one split"),
        ("data_digest", "the same data"),
    ):
        if len({getattr(card.run, field) for card in cards}) > 1:
            raise ValueError(f"the passes read together are of {says}")
    if not all(card.complete for card in cards):
        raise ValueError("every pass read is complete")
    keyed = [{(r.item, r.variant): r for r in results} for _, results in passes]
    if len({frozenset(found) for found in keyed}) > 1:
        raise ValueError("the passes read together hold the same variants")
    off = [n for n, card in enumerate(cards) if card.run.classifier == "off"]
    if len(off) != 2:
        raise ValueError("the reading needs two off passes, exactly")
    first, second = keyed[off[0]], keyed[off[1]]
    allowed = max(cards[n].card.paused.cut_offs for n in off) + 1
    readings: list[Reading] = []
    for n, card in enumerate(cards):
        if n in off:
            continue
        diffs, own, unpaired = [], [], 0
        for key, result in keyed[n].items():
            ends = [r.turns for r in (result, first[key], second[key])]
            if len({len(t) for t in ends}) > 1:
                unpaired += 1
                continue
            for mine, one, two in zip(*ends, strict=True):
                diffs.append(mine.end_ms - (one.end_ms + two.end_ms) / 2)
                own.append(two.end_ms - one.end_ms)
        delay = statistics.median(diffs) if diffs else None
        off_ms = abs(statistics.median(own)) if own else None
        cut_offs = card.card.paused.cut_offs
        holds = None
        if delay is not None and off_ms is not None:
            slower = delay > DELAY_BOUND_MS and delay > off_ms
            holds = cut_offs <= allowed and not slower
        readings.append(
            Reading(
                run=card.run.name,
                classifier=card.run.classifier,
                cut_offs=cut_offs,
                allowed=allowed,
                pairs=len(diffs),
                unpaired=unpaired,
                delay_ms=delay,
                off_ms=off_ms,
                holds=holds,
            )
        )
    return tuple(readings)
