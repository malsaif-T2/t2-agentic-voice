"""Rules for every Python module in the repository, layered or not (`uv run poe arch`).

  ARCH-SIZE    modules stay at or under [modules] max_lines lines (harness.toml)
  ARCH-FMT     `# fmt: skip` only ends a module- or class-level data assignment: the formatter
               owns layout, except for hand-aligned data tables
  ARCH-PARSE   every module is valid Python

check_architecture.py applies them to src/ together with the layer rules, and check_support
applies them alone to the support folders ([modules] support_dirs: scripts/ and tests/).
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

from scripts._common import Violation


def parse_module(
    display: str, source: str, max_lines: int
) -> tuple[ast.Module | None, list[Violation]]:
    """The module's tree (None if it does not parse) and its size and layout violations."""
    violations: list[Violation] = []
    line_count = len(source.splitlines())
    if line_count > max_lines:
        violations.append(
            Violation(
                display,
                max_lines + 1,
                "ARCH-SIZE",
                f"module has {line_count} lines (max {max_lines})",
                "Split the module by responsibility into smaller modules (in the same layer "
                "for src/).",
            )
        )
    try:
        tree = ast.parse(source, filename=display)
    except SyntaxError as exc:
        fix = "Fix the syntax error; the architecture check cannot analyze this file."
        violations.append(Violation(display, exc.lineno or 1, "ARCH-PARSE", str(exc.msg), fix))
        return None, violations
    return tree, violations + _fmt_skips(display, source, tree)


def _fmt_skips(display: str, source: str, tree: ast.Module) -> list[Violation]:
    """The formatter owns layout, except for hand-aligned data tables."""
    owners: list[ast.Module | ast.ClassDef] = [tree]
    owners += [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    data_ends = {
        node.end_lineno
        for owner in owners
        for node in owner.body
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.TypeAlias)
    }
    return [
        Violation(
            display,
            token.start[0],
            "ARCH-FMT",
            "`# fmt: skip` on code rather than on a data table",
            "Remove it and run `uv run poe fmt`. Keep `# fmt: skip` only at the end of a "
            "module- or class-level assignment of hand-aligned data.",
        )
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
        and "fmt: skip" in token.string
        and token.start[0] not in data_ends
    ]


def check_support(root: Path, dirs: tuple[str, ...], max_lines: int) -> tuple[list[Violation], int]:
    """The support folders (scripts/, tests/): the size and layout rules only."""
    files = sorted(p for d in dirs for p in (root / d).rglob("*.py"))
    violations: list[Violation] = []
    for path in files:
        display = path.relative_to(root).as_posix()
        violations.extend(parse_module(display, path.read_text(encoding="utf-8"), max_lines)[1])
    return violations, len(files)
