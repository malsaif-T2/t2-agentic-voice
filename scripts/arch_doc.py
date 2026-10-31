"""ARCH-DOC, for the architecture check (scripts/check_architecture.py): the architecture doc's
layer table says what harness.toml enforces, row by row.

The table is the one whose header row starts with `| Layer |` and has a `May import` column and
an `Owns` column (a header may go on, as in `Owns (only it may import)`). Each row names one
layer, in backticks, in its first cell. `May import` lists the other layers it may import
([layers]), and `Owns` the libraries [[owners]] gives it; a cell lists names in backticks or
separated by commas, and `none` or `—` means none. The other columns are prose and are not read.

What it cannot see: whether the reason for a change was recorded in a decision. That stays a
review (docs/design/decisions.md).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.harness_config import ArchConfig

_TICKED = re.compile(r"`([^`]+)`")
_NONE = frozenset({"", "none", "—", "-"})
FIX = (
    "Make the row and harness.toml agree: change the row, or [layers] and [[owners]] in "
    "harness.toml, in the same commit, and record why in docs/design/decisions.md."
)


@dataclass(frozen=True)
class Row:
    line: int
    layer: str
    imports: frozenset[str]
    owns: frozenset[str]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _names(cell: str) -> frozenset[str]:
    ticked = _TICKED.findall(cell)
    items = ticked if ticked else cell.split(",")
    return frozenset(item.strip() for item in items if item.strip().lower() not in _NONE)


def layer_table(text: str) -> tuple[int, list[Row]] | None:
    """(the header's line, the rows) of the doc's layer table, or None without one."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        cells = _cells(line) if line.lstrip().startswith("|") else []
        if not cells or cells[0] != "Layer":
            continue
        imports = next((i for i, c in enumerate(cells) if c.startswith("May import")), None)
        owns = next((i for i, c in enumerate(cells) if c.startswith("Owns")), None)
        if imports is None or owns is None:
            continue
        return index + 1, list(_rows(lines, index + 2, imports, owns))
    return None


def _rows(lines: list[str], start: int, imports: int, owns: int) -> Iterator[Row]:
    """The table's rows from `start` (the line after its separator), until a non-table line."""
    for index in range(start, len(lines)):
        if not lines[index].lstrip().startswith("|"):
            return
        cells = _cells(lines[index])
        cells += [""] * (max(imports, owns) + 1 - len(cells))
        first = _TICKED.findall(cells[0])
        layer = first[0] if first else cells[0]
        yield Row(index + 1, layer, _names(cells[imports]), _names(cells[owns]))


def check_layer_doc(root: Path, arch: ArchConfig) -> list[Violation]:
    """ARCH-DOC: one row per layer of harness.toml, each with that layer's imports and owned
    libraries; no row for a layer the config does not have."""
    doc = root / arch.architecture_doc
    if not arch.architecture_doc or not doc.is_file():
        return []  # turned off, or missing: the docs check reports a missing required doc
    shown = arch.architecture_doc
    table = layer_table(doc.read_text(encoding="utf-8"))
    if table is None:
        fix = (
            f"Add the layer table to {shown}: a header `| Layer | Responsibility | May import | "
            "Owns (only it may import) |`, then one row per layer of [layers] in harness.toml."
        )
        return [Violation(shown, 1, "ARCH-DOC", "the layer table is missing", fix)]
    header, rows = table
    violations: list[Violation] = []
    seen: set[str] = set()
    for row in rows:
        if row.layer in seen:
            problem = f"layer '{row.layer}' has two rows in the layer table"
            violations.append(Violation(shown, row.line, "ARCH-DOC", problem, FIX))
            continue
        seen.add(row.layer)
        violations += _compare(shown, row, arch)
    for layer in arch.layers:
        if layer not in seen:
            problem = f"layer '{layer}' of harness.toml has no row in the layer table"
            fix = (
                f"Add a row for it (what it is for, what it may import, what it owns), or "
                f"remove it from [layers] in harness.toml. {FIX}"
            )
            violations.append(Violation(shown, header, "ARCH-DOC", problem, fix))
    return violations


def _compare(shown: str, row: Row, arch: ArchConfig) -> list[Violation]:
    if row.layer not in arch.layers:
        problem = f"the layer table has a row for '{row.layer}', which is not in [layers]"
        return [Violation(shown, row.line, "ARCH-DOC", problem, FIX)]
    found = []
    imports = arch.layers[row.layer] - {row.layer}
    if row.imports != imports:
        problem = (
            f"layer '{row.layer}' may import {_listed(imports)} in harness.toml, but its row "
            f"says {_listed(row.imports)}"
        )
        found.append(Violation(shown, row.line, "ARCH-DOC", problem, FIX))
    owned = frozenset(name for name, o in arch.owners.items() if row.layer in o.layers)
    if row.owns != owned:
        problem = (
            f"layer '{row.layer}' owns {_listed(owned)} in harness.toml's [[owners]], but its "
            f"row says {_listed(row.owns)}"
        )
        found.append(Violation(shown, row.line, "ARCH-DOC", problem, FIX))
    return found


def _listed(names: frozenset[str]) -> str:
    return "[" + ", ".join(sorted(names)) + "]" if names else "nothing"
