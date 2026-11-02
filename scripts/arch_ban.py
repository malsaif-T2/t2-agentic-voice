"""ARCH-BAN, for the architecture check (scripts/check_architecture.py): the code a ban covers
never imports a module it bans, whichever layer owns the module's library (the design's 12.4).

ARCH-OWNER gives a whole library to its layers, matched on its top-level name, so it cannot say
"Pipecat in `voice`, but not its provider services". A [[bans]] table in harness.toml names
module prefixes instead:
- `modules`: each banned module, with every module under it (`pipecat.services` bans
  `pipecat.services.groq.stt`);
- `allowed`: modules inside those that stay allowed, each with every module under it;
- `within`: the code the ban covers, as module prefixes: the library's package (all of it, the
  package root and the facades included), a part of it (`t2_agentic_voice.voice.session`), or an
  app's package ([[apps]] name);
- `fix`: what to do instead, printed with every violation.

An import is read as ARCH-LAYER reads one: `import a.b`; `from a import b`, judged as the module
`a.b`, so that `from pipecat.services import groq` is banned and `from pipecat.services import
stt_service` is not (a name that is not a module falls under its module's ban); and an
`importlib.import_module` or `__import__` of a literal name. A relative import stays inside its
own package, which no ban names, and a module that does not parse is left to ARCH-PARSE.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from scripts._common import Violation
from scripts.arch_module import literal_import
from scripts.harness_arch import ArchConfig, Ban, under


class _Imports(ast.NodeVisitor):
    """Every module a tree imports, as (dotted name, line), in the order they appear."""

    def __init__(self) -> None:
        self.found: list[tuple[str, int]] = []
        self.loaders = {"__import__"}  # names that load a module named by a string
        self.importlibs = {"importlib"}  # names bound to the importlib module

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.found.append((alias.name, node.lineno))
            if alias.name == "importlib":
                self.importlibs.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module:
            return
        for alias in node.names:
            name = node.module if alias.name == "*" else f"{node.module}.{alias.name}"
            self.found.append((name, node.lineno))
            if node.module == "importlib" and alias.name == "import_module":
                self.loaders.add(alias.asname or alias.name)

    def visit_Call(self, node: ast.Call) -> None:
        if (name := literal_import(node, self.loaders, self.importlibs)) is not None:
            self.found.append((name, node.lineno))
        self.generic_visit(node)


def imported(tree: ast.Module) -> list[tuple[str, int]]:
    """(module, line) of each import in the tree, as ARCH-BAN judges it (the docstring above)."""
    visitor = _Imports()
    visitor.visit(tree)
    return visitor.found


def check_bans(root: Path, arch: ArchConfig) -> list[Violation]:
    """Each import that a ban covering its module forbids, in the library and every app."""
    products = [(arch.package, arch.package_dir)] + [(app.name, app.dir) for app in arch.apps]
    violations: list[Violation] = []
    for package, folder in products:
        bans = [b for b in arch.bans if any(under(w, package) for w in b.within)]
        for path, module in _modules(root / folder, package) if bans else ():
            covering = [(ban, scope) for ban in bans if (scope := ban.scope(module))]
            if covering:
                violations += _check_module(root, path, covering)
    return violations


def _modules(folder: Path, package: str) -> Iterator[tuple[Path, str]]:
    """Each Python file under the package's folder, with its dotted module name."""
    for path in sorted(folder.rglob("*.py")):
        parts = path.relative_to(folder).with_suffix("").parts
        if "__pycache__" not in parts:
            yield path, ".".join((package, *parts[: -1 if parts[-1] == "__init__" else None]))


def _check_module(root: Path, path: Path, covering: list[tuple[Ban, str]]) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []  # ARCH-PARSE reports it
    display = path.relative_to(root).as_posix()
    found = []
    for name, line in imported(tree):
        for ban, scope in covering:
            if (prefix := ban.banned(name)) is not None:
                problem = f"'{name}' is banned in '{scope}' ([[bans]]: '{prefix}')"
                found.append(Violation(display, line, "ARCH-BAN", problem, ban.fix))
    return found
