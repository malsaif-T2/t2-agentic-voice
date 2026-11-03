"""The tables of `docs/generated/eval-history.md` beside `poe eval`'s own (history.py renders the
page): a table for each kind of run that has one, end-of-turn, timing and overlap runs, and each
run's numbers by stratum value; with the cell helpers every table writes with, so a note renders
as the text it is.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from ole5_voice.evals.run_lines import AnyLine, EotLine, OverlapLine, TimingLine
from ole5_voice.evals.runs import HistoryLine

# Markdown's own characters, escaped in a cell so a note renders as the text it is: no link, no
# HTML, no table cell of its own.
_MARKDOWN: Final = re.compile(r"([\\`*\[\](){}<>|~&])")


def strata(line: AnyLine) -> list[str]:
    """A run's numbers by stratum value: accuracy for `poe eval`'s, cut-offs and misses for an
    end-of-turn run's, each with its items; each step's median for a timing run's; the right
    verdicts, stops and false stops, then whether each target held, for an overlap run's."""
    if isinstance(line, HistoryLine):
        header = "| Stratum | Value | Items | Accuracy |\n| --- | --- | --- | --- |"
        rows = [
            row(cell(stratum), cell(value), str(shown.items), percent(shown.accuracy))
            for stratum, values in sorted(line.breakdowns.items())
            for value, shown in sorted(values.items())
        ]
    elif isinstance(line, EotLine):
        header = (
            "| Stratum | Value | Items | Variants | Cut-offs | Misses |\n"
            "| --- | --- | --- | --- | --- | --- |"
        )
        rows = [
            row(cell(stratum), cell(value), *map(str, (c.items, c.variants, c.cut_offs, c.misses)))
            for stratum, values in sorted(line.breakdowns.items())
            for value, c in sorted(values.items())
        ]
    elif isinstance(line, TimingLine):
        header = "| Step | Median (ms) |\n| --- | --- |"
        rows = [row(cell(step), ms(median)) for step, median in line.medians_ms.items()]
    else:
        return _overlap_strata(line)
    return ["", header, *rows] if rows else []


def _overlap_strata(line: OverlapLine) -> list[str]:
    header = (
        "| Stratum | Value | Items | Variants | Right | Stopped of those that should "
        "| False stops |\n| --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        row(
            cell(stratum),
            cell(value),
            str(c.items),
            str(c.variants),
            str(c.right),
            f"{c.stopped} of {c.should_stop}",
            f"{c.false_stops} of {c.should_go_on}",
        )
        for stratum, values in sorted(line.breakdowns.items())
        for value, c in sorted(values.items())
    ]
    held = {True: "holds", False: "fails", None: "—"}
    targets = [row(cell(name), held[holds]) for name, holds in line.targets.items()]
    found = ["", header, *rows] if rows else []
    return found + (["", "| Target | Held |\n| --- | --- |", *targets] if targets else [])


def eot_rows(lines: Sequence[tuple[int, EotLine]]) -> list[str]:
    """The end-of-turn runs' table, when there is one."""
    if not lines:
        return []
    return [
        "\n## End-of-turn runs\n",
        "| # | Time | Run | Commit | Answerer | Split | Items | Variants | Cut-offs | Misses "
        "| Median delay (ms) | 90th percentile (ms) | Secondary cut-offs | Complete |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *(
            row(
                str(number),
                line.time.isoformat(timespec="seconds"),
                line.run,
                line.commit,
                line.answerer,
                line.split,
                str(line.items),
                str(line.variants),
                str(line.cut_offs),
                str(line.misses),
                ms(line.delay_median_ms),
                ms(line.delay_p90_ms),
                "—"
                if line.secondary is None
                else f"{line.secondary.cut_offs} of {line.secondary.variants}",
                "yes" if line.complete else "no",
            )
            for number, line in lines
        ),
    ]


def timing_rows(lines: Sequence[tuple[int, TimingLine]]) -> list[str]:
    """The timing runs' table, when there is one."""
    if not lines:
        return []
    return [
        "\n## Timing runs\n",
        "| # | Time | Run | Commit | Split | Variants | Cut into turns | Failures | Requests "
        "| Billed seconds | Cost | Complete |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *(
            row(
                str(number),
                line.time.isoformat(timespec="seconds"),
                line.run,
                line.commit,
                line.split,
                str(line.variants),
                str(line.cut_variants),
                str(line.failures),
                cell(", ".join(f"{m} {n}" for m, n in sorted(line.requests.items()))),
                f"{line.billed_seconds:.1f}",
                f"${line.cost_usd:.4f}",
                "yes" if line.complete else "no",
            )
            for number, line in lines
        ),
    ]


def overlap_rows(lines: Sequence[tuple[int, OverlapLine]]) -> list[str]:
    """The overlap runs' table, when there is one."""
    if not lines:
        return []
    return [
        "\n## Overlap runs\n",
        "| # | Time | Run | Commit | Answerer | Split | Items | Variants | Failed | Right "
        "| Stop median (ms) | 90th percentile (ms) | Most requests | Targets held | Requests "
        "| Billed seconds | Cost | Complete |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
        "| --- | --- | --- | --- |",
        *(
            row(
                str(number),
                line.time.isoformat(timespec="seconds"),
                line.run,
                line.commit,
                line.answerer,
                line.split,
                str(line.items),
                str(line.variants),
                str(line.failed),
                str(line.right),
                ms(line.stop_median_ms),
                ms(line.stop_p90_ms),
                "—" if line.requests_max is None else str(line.requests_max),
                f"{sum(held is True for held in line.targets.values())} of {len(line.targets)}",
                str(line.requests),
                f"{line.billed_seconds:.1f}",
                f"${line.cost_usd:.4f}",
                "yes" if line.complete else "no",
            )
            for number, line in lines
        ),
    ]


def ms(value: float | None) -> str:
    """A time in whole milliseconds, or a dash for none."""
    return "—" if value is None else f"{value:.0f}"


def row(*cells: str) -> str:
    """One table row of `cells`."""
    return "| " + " | ".join(cells) + " |"


def cell(text: str) -> str:
    """`text` as one table cell: on one line, Markdown's own characters escaped."""
    return _MARKDOWN.sub(r"\\\1", " ".join(text.split())) or "—"


def percent(rate: float | None) -> str:
    """A share as a percentage to a tenth, or a dash for none."""
    return "—" if rate is None else f"{rate:.1%}"
