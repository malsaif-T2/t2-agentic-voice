"""The quality score per layer (scripts/quality.py): what each signal measures, how they weigh,
that a layer without coverage data is graded on the rest, that each app is graded as one unit,
and that a layer with no code is graded empty."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.gc_due import compare
from scripts.quality import (
    EMPTY,
    Signals,
    grade,
    grades,
    layer_of,
    letter,
    recorded_grades,
    render,
    score,
)
from tests.harness.support import SYNTHETIC, config

DOC = '"""What this module is for."""\n'
WEIGHTS = {"coverage": 40, "size": 20, "suppressions": 15, "duplication": 15, "docstrings": 10}
LAYERS = ("core", "domain", "adapters", "services", "api")
SHOP = '\n[[apps]]\nname = "shop"\nroot = "apps/shop/src"\n'


@pytest.mark.parametrize(
    ("path", "layer"),
    [
        ("src/app/adapters/store.py", "adapters"),
        ("src/app/adapters/files/reader.py", "adapters"),
        ("src/app/__init__.py", None),
        ("src/app/elsewhere/x.py", None),
        ("scripts/tool.py", "scripts"),
        ("tests/core/test_x.py", None),
        ("apps/shop/src/shop/orders/cart.py", "shop"),
        ("apps/shop/src/other/x.py", None),
    ],
)
def test_each_module_belongs_to_its_layer_or_its_app(
    tmp_path: Path, path: str, layer: str | None
) -> None:
    assert layer_of(path, config(tmp_path, SYNTHETIC + SHOP)) == layer


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
    shown = {g.layer: (g.letter, g.coverage is not None) for g in every if g.letter != EMPTY}
    assert recorded_grades(table) == shown
    assert set(shown) == {"core", "api"}  # the empty layers are no grade to compare


def test_each_app_is_one_unit_between_the_layers_and_the_scripts(tmp_path: Path) -> None:
    loaded = config(tmp_path, SYNTHETIC + SHOP)
    sources = {
        "apps/shop/src/shop/a.py": DOC + "x = 1\n",
        "apps/shop/src/shop/orders/b.py": DOC + "y = 2\n" * 40,  # above the watch
        "scripts/tool.py": DOC + "z = 3\n",
    }
    every = grades(sources, {}, loaded)
    assert [g.layer for g in every] == [*LAYERS, "shop", "scripts"]
    shop = every[len(LAYERS)]
    assert (shop.modules, shop.small) == (2, 0.5)
    assert shop.largest[1] == "apps/shop/src/shop/orders/b.py"


def test_a_layer_with_no_code_is_graded_empty_and_never_compared(tmp_path: Path) -> None:
    """A docstring-only `__init__.py` counts in neither share: alone it leaves its layer empty,
    and beside a module it does not halve the size share (the adapters layer had both)."""
    loaded = config(tmp_path)
    sources = {
        "src/app/core/__init__.py": DOC,
        "src/app/adapters/__init__.py": DOC,
        "src/app/adapters/big.py": DOC + "x = 1\n" * 40,
        "src/app/domain/__init__.py": DOC + "from app.domain.rules import rule\n",  # code
    }
    core, domain, adapters = (grade(sources, {}, layer, loaded) for layer in LAYERS[:3])
    assert (core.letter, core.modules) == (EMPTY, 0)
    assert domain.letter != EMPTY
    assert (adapters.modules, adapters.small) == (1, 0.0)
    assert "| core | empty | - | - | - | - | - | - | - |" in render([core], 30)
    recorded = {"core": ("A", False)}
    assert compare(recorded, [core]) == ([], [])  # code gone is no drop
