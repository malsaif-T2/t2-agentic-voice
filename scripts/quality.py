"""A quality score per layer: `uv run poe quality`, after `uv run poe check`. Its settings are
harness.toml's [quality] (and [gc] size_watch, [layers], [[apps]]).

Each layer of src/<package>/ ([layers] in harness.toml), each app as one unit ([[apps]]), and
scripts/, is graded from mechanical signals:
- coverage: the share of its statements the last test run executed (the `.coverage` file that
  `poe test` and `poe check` write), over the modules it measured;
- size: the share of its modules at or under [gc] size_watch lines;
- suppressions: `noqa`, `type: ignore`, and `pragma: no cover` per 1,000 lines (`fmt: skip`
  marks data tables, so it does not count);
- duplication: runs of repeated tokens that touch the layer (the detector of `poe gc`), the
  copies between an app and the library included;
- docstrings: the share of its modules that say what they are for.

A module that holds only its docstring (an empty layer's `__init__.py`) counts in neither
share, and a unit with no module that holds code is graded `empty`, not A.

Score = [quality.weights] over those signals, each from 0 to 1, rescaled when coverage is
unknown; grade A from 90, B from 80, C from 70, D below. The grades, and each layer's gaps in
words, are kept in docs/harness/quality.md and refreshed in every garbage-collection round.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.gc_report import Duplicate, duplicates, python_sources, suppressions
from scripts.harness_config import HarnessConfig, load_or_report

ROOT = Path(__file__).resolve().parents[1]
COUNTED = ("# noqa", "# type: ignore", "# pragma: no cover")
LETTERS = ((90, "A"), (80, "B"), (70, "C"), (0, "D"))
NOT_MEASURED = "not measured"
# The grade of a unit with no module that holds code (a layer of only a docstring `__init__.py`).
EMPTY = "empty"
# A row of the grade table: layer, letter, score, coverage (render writes it).
_RECORDED = re.compile(
    rf"^\| (\w+) \| \*\*([{''.join(g for _, g in LETTERS)}])\*\* \| \d+ \| ([^|]+) \|",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Signals:
    """Each from 0 to 1; coverage is None when it was not measured."""

    coverage: float | None
    size: float
    suppressions: float
    duplication: float
    docstrings: float


def score(signals: Signals, weights: Mapping[str, int]) -> float:
    known = {k: v for k, v in vars(signals).items() if v is not None}
    weight = sum(weights[k] for k in known)
    return 100 * sum(weights[k] * v for k, v in known.items()) / weight if weight else 0.0


def letter(value: float) -> str:
    return next(grade for floor, grade in LETTERS if value >= floor)


@dataclass(frozen=True)
class Grade:
    layer: str
    modules: int
    lines: int
    coverage: float | None  # 0 to 1, or None when not measured
    small: float  # share of modules within the size watch
    largest: tuple[int, str]  # (lines, module)
    suppressions_per_kloc: float
    duplicate_runs: int
    docstrings: float
    score: float
    letter: str


def layer_of(path: str, config: HarnessConfig) -> str | None:
    """The unit a module is graded in: its layer of the library, its app ([[apps]] name), or
    scripts; None for any other (the package root and its facades, tests/)."""
    if path.startswith("scripts/"):
        return "scripts"
    for app in config.arch.apps:
        if path.startswith(f"{app.dir}/"):
            return app.name
    parts, depth = path.split("/"), len(config.package_dir.split("/"))
    inside = path.startswith(f"{config.package_dir}/") and len(parts) > depth + 1
    return parts[depth] if inside and parts[depth] in config.arch.layers else None


def units(config: HarnessConfig) -> tuple[str, ...]:
    """What `poe quality` grades, in its table's order: the layers, the apps, then scripts."""
    return (*config.arch.layers, *(app.name for app in config.arch.apps), "scripts")


def has_code(source: str) -> bool:
    """Whether a module holds more than its docstring: a docstring-only `__init__.py` is no
    module for the size and docstring shares, nor a reason to grade a layer."""
    tree = ast.parse(source)
    return len(tree.body) > int(ast.get_docstring(tree) is not None)


def grade(
    sources: dict[str, str],
    coverage: dict[str, tuple[int, int]],
    layer: str,
    config: HarnessConfig,
    runs: Sequence[Duplicate] | None = None,
) -> Grade:
    """`sources`: path -> text for the library, the apps and scripts/; `coverage`: path ->
    (statements, missed), for the measured files; `runs`: the duplicates in `sources`, when
    already found. A unit with no module that holds code is graded EMPTY."""
    rules = config.quality
    mine = {p: t for p, t in sources.items() if layer_of(p, config) == layer}
    coded = {p: t for p, t in mine.items() if has_code(t)}
    sizes = {path: len(text.splitlines()) for path, text in coded.items()}
    lines = sum(len(text.splitlines()) for text in mine.values())
    counts, _ = suppressions(mine)
    suppressed = sum(c[kind] for c in counts.values() for kind in COUNTED)
    found = duplicates(sources, config.gc.min_tokens) if runs is None else runs
    places = ((d.first.split(":")[0], d.second.split(":")[0]) for d in found)
    mine_runs = [pair for pair in places if layer in {layer_of(path, config) for path in pair}]
    measured = [coverage[path] for path in mine if path in coverage]
    statements = sum(s for s, _ in measured)
    modules = max(len(coded), 1)
    per_kloc = 1000 * suppressed / lines if lines else 0.0
    signals = Signals(
        coverage=1 - sum(m for _, m in measured) / statements if statements else None,
        size=sum(1 for n in sizes.values() if n <= config.gc.size_watch) / modules,
        suppressions=max(0.0, 1 - per_kloc / rules.suppressions_floor),
        duplication=max(0.0, 1 - len(mine_runs) / rules.duplication_floor),
        docstrings=sum(1 for t in coded.values() if ast.get_docstring(ast.parse(t))) / modules,
    )
    value = score(signals, rules.weights)
    return Grade(
        layer=layer,
        modules=len(coded),
        lines=lines,
        coverage=signals.coverage,
        small=signals.size,
        largest=max(((n, path) for path, n in sizes.items()), default=(0, "-")),
        suppressions_per_kloc=per_kloc,
        duplicate_runs=len(mine_runs),
        docstrings=signals.docstrings,
        score=value,
        letter=letter(value) if coded else EMPTY,
    )


def grades(
    sources: dict[str, str], coverage: dict[str, tuple[int, int]], config: HarnessConfig
) -> list[Grade]:
    """Every unit's grade (`units`). The duplicates are found once for all."""
    runs = duplicates(sources, config.gc.min_tokens)
    return [grade(sources, coverage, unit, config, runs) for unit in units(config)]


def read_sources(root: Path, config: HarnessConfig) -> dict[str, str]:
    """path -> text, for every module of the library, of each app, and of scripts/."""
    return python_sources(root, (*config.product_dirs, "scripts"))


def measured_coverage(root: Path) -> dict[str, tuple[int, int]]:
    """(statements, missed) per file, from the last test run's coverage data; empty without it."""
    data_file = root / ".coverage"
    if not data_file.is_file():
        return {}
    from coverage import Coverage  # a dev dependency, needed only here

    cov = Coverage(data_file=str(data_file), config_file=False)
    cov.load()
    found = {}
    for path in cov.get_data().measured_files():
        _name, statements, _excluded, missed, _text = cov.analysis2(path)
        resolved = Path(path).resolve()
        if resolved.is_relative_to(root.resolve()):
            found[resolved.relative_to(root.resolve()).as_posix()] = (len(statements), len(missed))
    return found


def render(grades: Sequence[Grade], size_watch: int) -> str:
    """The grade table that docs/harness/quality.md keeps, and recorded_grades reads back."""
    lines = [
        f"| Layer | Grade | Score | Coverage | Modules within {size_watch} lines | Largest "
        "| Suppressions per 1,000 lines | Duplicate runs | Docstrings |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for g in grades:
        if g.letter == EMPTY:
            lines.append(f"| {g.layer} | {EMPTY} |{' - |' * 7}")
            continue
        coverage = f"{g.coverage:.0%}" if g.coverage is not None else NOT_MEASURED
        lines.append(
            f"| {g.layer} | **{g.letter}** | {g.score:.0f} | {coverage} | {g.small:.0%} "
            f"| {g.largest[0]} `{g.largest[1].split('/')[-1]}` | {g.suppressions_per_kloc:.1f} "
            f"| {g.duplicate_runs} | {g.docstrings:.0%} |"
        )
    return "\n".join(lines) + "\n"


def recorded_grades(text: str) -> dict[str, tuple[str, bool]]:
    """Each layer's letter in a table `render` wrote, and whether its coverage was measured
    (`poe gc` compares them with the grades now)."""
    return {
        layer: (letter, coverage.strip() != NOT_MEASURED)
        for layer, letter, coverage in _RECORDED.findall(text)
    }


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="Grade each layer's quality.").parse_args(argv)
    config = load_or_report("quality", ROOT)
    if config is None:
        return 1
    coverage = measured_coverage(ROOT)
    if not coverage:
        print("No coverage data (.coverage): run `uv run poe test` first for the full score.\n")
    found = grades(read_sources(ROOT, config), coverage, config)
    print(render(found, config.gc.size_watch), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
