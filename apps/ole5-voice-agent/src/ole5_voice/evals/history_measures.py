"""The tables of `docs/generated/eval-history.md` for plan 006's runs (history.py renders the
page; history_tables.py holds the other kinds' tables and the cell helpers): a table for each
kind that has a run, K's talker runs, S's scenario runs, U's uncertain-middle runs and T's
first-audio runs, and each run's numbers by stratum value, its targets and its prices. Of these
runs only T bills audio, so only its section shows a price per hour.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from ole5_voice.evals.first_audio_score import PathStats, ReplyPath
from ole5_voice.evals.history_tables import cell, ms, percent, row
from ole5_voice.evals.measure_lines import FirstAudioLine, UncertainLine
from ole5_voice.evals.talker_lines import ScenarioLine, TalkerLine

MeasureLine = TalkerLine | ScenarioLine | UncertainLine | FirstAudioLine
_HELD: Final = {True: "holds", False: "fails", None: "—"}
_TALKER: Final = (
    "| # | Time | Run | Commit | Arm | Model | Split | Items | Variants | Failures | Answers "
    "| Honest | Retrieval | Language | First clause, model (s) | First clause, wall clock (s) "
    "| Violations | Cost | Complete |"
)
_SCENARIOS: Final = (
    "| # | Time | Run | Commit | Model | Repeats | Scenarios | Plays | Failures | Passing plays "
    "| Targets met | Violations | Cost | Complete |"
)
_UNCERTAIN: Final = (
    "| # | Time | Run | Commit | Source | Model | Overlaps | Failed | Right, U0 | Right, arm "
    "| Listening stops, U0 | Listening stops, arm | Answer median (ms) | p | Kept | Cost "
    "| Complete |"
)
_FIRST_AUDIO: Final = (
    "| # | Time | Run | Commit | Split | Tools | Variants | No search median (ms) "
    "| No search 90th (ms) | Search median (ms) | Search 90th (ms) | Progress late "
    "| Targets held | Billed seconds | Cost | Complete |"
)


def table(title: str, header: str, rows: Sequence[str]) -> list[str]:
    """A table of `rows` under `title` and its `header` (one row of column names), with the
    separator its columns need; nothing without a row."""
    if not rows:
        return []
    columns = header.count("|") - 1
    return [f"\n## {title}\n", header + "\n" + "| --- " * columns + "|", *rows]


def _block(header: str, rows: Sequence[str]) -> list[str]:
    """`table`'s rows without a title, after an empty line."""
    found = table("", header, rows)
    return ["", *found[1:]] if found else []


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def _time(line: MeasureLine) -> str:
    return line.time.isoformat(timespec="seconds")


def _times(paths: Mapping[ReplyPath, PathStats]) -> list[str]:
    """Each path's median and 90th percentile, the path with no search first."""
    found = [paths.get(path) for path in ("no_search", "search")]
    return [ms(None if p is None else value) for p in found for value in _spread(p)]


def _spread(stats: PathStats | None) -> tuple[float | None, float | None]:
    return (None, None) if stats is None else (stats.median_ms, stats.p90_ms)


def talker_rows(lines: Sequence[tuple[int, TalkerLine]]) -> list[str]:
    """Run K's table, when it has a run: the first clause's median by the model's own time
    (the keep rule's, Q15) beside the wall clock's."""
    rows = [
        row(
            *(str(n), _time(line), line.run, line.commit, line.arm, cell(line.model), line.split),
            *map(str, (line.items, line.variants, line.failures)),
            *map(percent, (line.answers, line.honest, line.retrieval, line.language)),
            _seconds(line.own_first_clause_median_s),
            _seconds(line.first_clause_median_s),
            str(line.violations),
            f"${line.cost_usd:.4f}",
            _yes(line.complete),
        )
        for n, line in lines
    ]
    return table("Talker runs", _TALKER, rows)


def scenario_rows(lines: Sequence[tuple[int, ScenarioLine]]) -> list[str]:
    """Run S's table, when it has a run."""
    rows = [
        row(
            str(n),
            _time(line),
            line.run,
            line.commit,
            cell(line.model),
            *map(str, (line.repeats, line.scenarios, line.plays, line.failures)),
            str(sum(line.passed.values())),
            "—" if line.targets_met is None else _yes(line.targets_met),
            str(line.violations),
            f"${line.cost_usd:.4f}",
            _yes(line.complete),
        )
        for n, line in lines
    ]
    return table("Scenario runs", _SCENARIOS, rows)


def uncertain_rows(lines: Sequence[tuple[int, UncertainLine]]) -> list[str]:
    """Run U's table, when it has a run: the rule's numbers (U0) beside the arm's."""
    rows = [
        row(
            str(n),
            _time(line),
            line.run,
            line.commit,
            line.source,
            cell(line.model),
            *map(str, (line.arm.variants, line.arm.failed, line.rule.right, line.arm.right)),
            *map(str, (line.rule.listening_stops, line.arm.listening_stops)),
            ms(line.arm.answer_median_ms),
            f"{line.p:.4f}",
            _yes(line.kept),
            f"${line.cost_usd:.4f}",
            _yes(line.complete),
        )
        for n, line in lines
    ]
    return table("Uncertain-middle runs", _UNCERTAIN, rows)


def first_audio_rows(lines: Sequence[tuple[int, FirstAudioLine]]) -> list[str]:
    """Run T's table, when it has a run."""
    rows = [
        row(
            str(n),
            _time(line),
            line.run,
            line.commit,
            line.split,
            "declared" if line.tools else "none",
            str(line.variants),
            *_times(line.paths),
            str(line.progress_late),
            f"{sum(held is True for held in line.targets.values())} of {len(line.targets)}",
            f"{line.billed_seconds:.1f}",
            f"${line.cost_usd:.4f}",
            _yes(line.complete),
        )
        for n, line in lines
    ]
    return table("First-audio runs", _FIRST_AUDIO, rows)


def measure_prices(line: MeasureLine) -> list[str]:
    """A run's prices, as its section's rows."""
    if isinstance(line, TalkerLine | ScenarioLine):
        priced = {m: f"${p.input_usd:g} in, ${p.output_usd:g} out" for m, p in line.prices.items()}
        return [
            row(f"Price per million tokens, {cell(model)}", text)
            for model, text in sorted(priced.items())
        ]
    if isinstance(line, UncertainLine):
        chat = line.prices
        found = []
    else:
        chat = line.chat_price_per_million_usd
        found = [row("Price per hour of audio", f"${line.price_per_hour_usd:g}")]
        found += [
            row(f"Price per million characters, {cell(model)}", f"${usd:g}")
            for model, usd in sorted(line.tts_price_per_million_usd.items())
        ]
    return found + [
        row(f"Price per million tokens, {cell(kind)}", f"${usd:g}")
        for kind, usd in sorted(chat.items())
    ]


def measure_strata(line: MeasureLine) -> list[str]:
    """A run's numbers by stratum value, then whether each target held."""
    if isinstance(line, ScenarioLine):
        rows = [row(cell(name), str(n)) for name, n in sorted(line.passed.items())]
        return _block("| Scenario | Passing plays |", rows)
    if isinstance(line, TalkerLine):
        header = "| Stratum | Value | Items | Variants | Failures | Answers | Passing |"
        rows = [
            row(
                *(cell(stratum), cell(value)),
                *map(str, (c.items, c.variants, c.failures)),
                *(percent(c.answers), percent(c.passed)),
            )
            for stratum, values in sorted(line.breakdowns.items())
            for value, c in sorted(values.items())
        ]
    elif isinstance(line, UncertainLine):
        header = (
            "| Stratum | Value | Items | Variants | Right | Stopped of those that should "
            "| False stops |"
        )
        rows = [
            row(
                *(cell(stratum), cell(value)),
                *map(str, (c.items, c.variants, c.right)),
                *(f"{c.stopped} of {c.should_stop}", f"{c.false_stops} of {c.should_go_on}"),
            )
            for stratum, values in sorted(line.breakdowns.items())
            for value, c in sorted(values.items())
        ]
    else:
        header = (
            "| Start of time | Items | Variants | No search median (ms) | No search 90th (ms) "
            "| Search median (ms) | Search 90th (ms) | Progress late |"
        )
        rows = [
            row(cell(end), str(g.items), str(g.variants), *_times(g.paths), str(g.progress_late))
            for end, g in sorted(line.ends.items())
        ]
    targets = [row(cell(name), _HELD[holds]) for name, holds in line.targets.items()]
    return _block(header, rows) + _block("| Target | Held |", targets)
