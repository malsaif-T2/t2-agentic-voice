"""The parts of `poe eval-compare`'s report (`compare.py`) that each run's own scorecard gives:
the header, naming both runs, their settings that differ and the one speaker; and the aggregates,
each metric and each stratum value's accuracy side by side with B's change, a held-out stratum
value only where both runs hold it over the same items. The variant-by-variant comparison and
the sign test are `compare.py`'s.
"""

from __future__ import annotations

from ole5_voice.evals.runs import HELD_OUT_MIN_ITEMS, Metrics, Scorecard


def header(a: Scorecard, b: Scorecard) -> list[str]:
    """The report's title and the table of both runs, then the settings that differ."""
    rows = [
        ("Run", a.run.name, b.run.name),
        ("Answerer", a.run.answerer, b.run.answerer),
        ("Model", a.run.model or "—", b.run.model or "—"),
        ("Split", a.run.split, b.run.split),
        ("Commit", a.run.commit, b.run.commit),
        ("Complete", _yes(a.complete), _yes(b.complete)),
    ]
    names = sorted(a.run.settings.keys() | b.run.settings.keys())
    differ = [
        f"{name} ({a.run.settings.get(name, 'unset')} in A, {b.run.settings.get(name, 'unset')}"
        " in B)"
        for name in names
        if a.run.settings.get(name) != b.run.settings.get(name)
    ]
    return [
        f"# {b.run.name} judged against {a.run.name}\n",
        "| | A, the baseline | B, the candidate |\n| --- | --- | --- |",
        *(f"| {label} | {first} | {second} |" for label, first, second in rows),
        "",
        f"Same commit and data: {a.run.commit}, data digest {a.run.data_digest[:12]}.",
        "Settings that differ: " + ("; ".join(differ) if differ else "none") + ".",
        "Every number describes one speaker, the owner (D-006).\n",
    ]


def aggregates(a: Scorecard, b: Scorecard) -> list[str]:
    """Each metric of both runs' totals, then each stratum value's accuracy, with B - A."""
    first, second = a.totals.model_dump(), b.totals.model_dump()
    lines = [
        "## Aggregates, each run's own scorecard\n",
        "| Metric | A | B | B - A |\n| --- | --- | --- | --- |",
        *(
            _compared(name, first[name], second[name], whole=field.annotation is int)
            for name, field in Metrics.model_fields.items()
        ),
        "",
        "| Stratum | Value | A accuracy | B accuracy | B - A |",
        "| --- | --- | --- | --- | --- |",
    ]
    strata = {(s, v) for card in (a, b) for s, values in card.breakdowns.items() for v in values}
    for stratum, value in sorted(strata):
        groups = [card.breakdowns.get(stratum, {}).get(value) for card in (a, b)]
        if a.run.split == "held-out" and not _same_items(*groups):
            continue
        accuracies = [group.accuracy if group else None for group in groups]
        lines.append(f"| {stratum} " + _compared(value, *accuracies))
    return lines


def _same_items(first: Metrics | None, second: Metrics | None) -> bool:
    """Whether both held-out runs hold a group over the same number of items, at least
    `HELD_OUT_MIN_ITEMS`, with no failure: at one data digest, the same items and variants, so
    B - A is never taken between groups that pool other items or variants, which would tell
    those between them apart (a failure moves an item's answered variants, and may pool it)."""
    return (
        first is not None
        and second is not None
        and first.items == second.items >= HELD_OUT_MIN_ITEMS
        and first.failures == second.failures == 0
    )


def _compared(label: str, first: float | None, second: float | None, *, whole: bool = False) -> str:
    """A table row of A's and B's value and B's change; `whole` for a count."""
    shown = "{:+.0f}" if whole else "{:+.4f}"
    change = "—" if first is None or second is None else shown.format(second - first)
    return f"| {label} | {_number(first, whole)} | {_number(second, whole)} | {change} |"


def _number(value: float | None, whole: bool) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}" if whole else f"{value:.4f}"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"
