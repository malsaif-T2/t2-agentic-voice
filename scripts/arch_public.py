"""ARCH-PUBLIC for the apps, for the architecture check (scripts/check_architecture.py): an app in
[[apps]] imports the library only through [package] public, and no other app.

It reads an app's import statements. `from <library> import <name>` imports a module when the
name is a layer or a facade ([package] facades), so that module must be public too; any other
name is a name the package root re-exports. The library's own side of the rule (it never imports
an app) is checked with its layers, in check_architecture.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts._common import Violation
from scripts.harness_arch import AppRule, ArchConfig
from scripts.harness_toml import CONFIG_FILE, RULE
from scripts.module_rules import parse_module


class _AppChecker(ast.NodeVisitor):
    """An app's import statements: the library only through its public modules, and no other
    app."""

    def __init__(self, arch: ArchConfig, *, app: str, display: str) -> None:
        self.arch = arch
        self.app = app
        self.display = display
        self.modules = arch.layers.keys() | arch.facade_names
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check(alias.name.split("."), node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module:
            base = node.module.split(".")
            # `from <library> import core` or `... import ports`: the name is a module, so
            # check it as one.
            if base == [self.arch.package]:
                for alias in node.names:
                    if alias.name in self.modules:
                        self._check([*base, alias.name], node.lineno)
            self._check(base, node.lineno)
        self.generic_visit(node)

    def _check(self, parts: list[str], line: int) -> None:
        module = ".".join(parts)
        if parts[0] in self.arch.app_names and parts[0] != self.app:
            problem = f"app '{self.app}' imports the app '{parts[0]}' ({module})"
            fix = "Apps share code only through the library: move it into its public API."
        elif parts[0] == self.arch.package and not self.arch.is_public(module):
            allowed = ", ".join(sorted(self.arch.public)) or "nothing"
            problem = f"'{module}' is not public; an app may import only: {allowed}"
            fix = (
                f"Import it from the library's public API (`from {self.arch.package} import "
                "...`). If apps need it, export it from the package root or a facade, or add "
                "the module to [package] public in harness.toml, and record why in "
                "docs/design/decisions.md."
            )
        else:
            return
        self.violations.append(Violation(self.display, line, "ARCH-PUBLIC", problem, fix))


def check_app(root: Path, app: AppRule, arch: ArchConfig) -> tuple[list[Violation], int]:
    """An app's modules: the module rules, and ARCH-PUBLIC."""
    app_dir = root / app.dir
    if not (app_dir / "__init__.py").is_file():
        init = f"{app.dir}/__init__.py"
        fix = f"Set this [[apps]] entry's name and root to the app's package, or create {init}."
        return [Violation(CONFIG_FILE, 1, RULE, f"{init} does not exist", fix)], 0
    violations: list[Violation] = []
    files = sorted(app_dir.rglob("*.py"))
    for path in files:
        display = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree, found = parse_module(display, source, arch.max_module_lines)
        if tree is not None:
            checker = _AppChecker(arch, app=app.name, display=display)
            checker.visit(tree)
            found += checker.violations
        violations += found
    return violations, len(files)
