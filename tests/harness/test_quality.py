"""The quality score per layer (scripts/quality.py): what each signal measures, how they weigh,
and that a layer without coverage data is graded on the rest."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.quality import (
    Signals,
    grade,
    grades,
    layer_of,
    letter,
    recorded_grades,
    render,
    score,
)
from tests.harness.support import config

DOC = '"""What this module is for."""\n'
WEIGHTS = {"coverage": 40, "size": 20, "suppressions": 15, "duplication": 15, "docstrings": 10}
LAYERS = ("core", "domain", "adapters", "services", "api")


@pytest.mark.parametrize(
    ("path", "layer"),
    [
        ("src/app/adapters/store.py", "adapters"),
        ("src/app/adapters/files/reader.py", "adapters"),
        ("src/app/__init__.py", None),
        ("src/app/elsewhere/x.py", None),
        ("scripts/tool.py", "scripts"),
        ("tests/core/test_x.py", None),
    ],
)
def test_each_module_belongs_to_its_layer(path: str, layer: str | None) -> None:
    assert layer_of(path, "src/app", LAYERS) == layer


PERFECT = Signals(coverage=1.0, size=1.0, suppressions=1.0, duplication=1.0, docstrings=1.0)


def test_the_signals_weigh_as_configured() -> None:
    assert (score(PERFECT, WEIGHTS), letter(score(PERFECT, WEIGHTS))) == (100, "A")
    assert score(replace(PERFECT, coverage=0.5), WEIGHTS) == 80  # coverage weighs 40
    assert score(replace(PERFECT, size=0.5), WEIGHTS) == 90  # size 20
    assert score(replace(PERFECT, suppressions=0.0), WEIGHTS) == 85  # 15
    assert score(replace(PERFECT, duplication=0.0), WEIGHTS) == 85  # 15
    assert score(replace(PERFECT, docstrings=0.0), WEIGHTS) == 90  # 10
    assert letter(score(replace(PERFECT, coverage=0.5, size=0.5), WEIGHTS)) == "C"
    assert [letter(v) for v in (90, 89.9, 80, 70, 69.9)] == ["A", "B", "B", "C", "D"]


def test_a_layer_without_coverage_is_graded_on_the_rest() -> None:
    assert score(replace(PERFECT, coverage=None), WEIGHTS) == 100
    unmeasured = replace(PERFECT, coverage=None, size=0.4)
    assert score(unmeasured, WEIGHTS) == pytest.approx(80)  # 20 of 60, 60% of it lost


def test_a_layer_is_measured_from_its_modules(tmp_path: Path) -> None:
    loaded = config(tmp_path)  # size watch 30 lines, ten suppressions per 1,000 lines is zero
    sources = {
        "src/app/adapters/a.py": DOC + "x = 1  # noqa: E501 - long data\n" * 9,
        "src/app/adapters/b.py": "y = 2\n" * 40,  # big, and no docstring
        "src/app/core/c.py": DOC + "z = 3\n",
    }
    coverage = {"src/app/adapters/a.py": (10, 1), "src/app/adapters/b.py": (30, 3)}
    found = grade(sources, coverage, "adapters", loaded)
    assert (found.modules, found.lines, found.largest) == (2, 50, (40, "src/app/adapters/b.py"))
    assert found.coverage == pytest.approx(36 / 40)
    assert (found.small, found.docstrings) == (0.5, 0.5)
    assert found.suppressions_per_kloc == pytest.approx(1000 * 9 / 50)
    assert grade(sources, {}, "core", loaded).coverage is None
    every = grades(sources, coverage, loaded)
    assert [g.layer for g in every] == [*LAYERS, "scripts"]
    assert every[2] == found
    table = render(every, loaded.gc.size_watch)
    assert "| Modules within 30 lines |" in table
    assert f"| adapters | **{found.letter}** |" in table


def test_the_table_reads_back_as_poe_gc_reads_it(tmp_path: Path) -> None:
    """What `render` writes into quality.md, `recorded_grades` reads: each layer's letter, and
    whether its coverage was measured, so the 'graded lower' signal never goes quiet."""
    loaded = config(tmp_path)
    sources = {"src/app/core/a.py": DOC + "x = 1\n", "src/app/api/b.py": DOC + "y = 2\n"}
    every = grades(sources, {"src/app/core/a.py": (1, 0)}, loaded)
    table = render(every, loaded.gc.size_watch)
    assert recorded_grades(table) == {g.layer: (g.letter, g.coverage is not None) for g in every}
