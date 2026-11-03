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
stt_service` is not (a name that is not a module falls under its module's ban); a relative
import, resolved against the module's package; and a call that loads a literal name
(`literal_import`). Every import counts, wherever it sits: in a function, a class, a `try` or
under `if TYPE_CHECKING:`.

A ban on a part of the library or an app also follows that package's own imports: a covered
module that imports one of the package's modules outside the ban, which imports a banned module
itself or through others of them, is refused at that import, with the chain that leads there.
So `voice/session/` cannot reach Pipecat through another `voice` module. Imports made inside a
banned library's own modules are not read (TD-043), and a module that does not parse is left to
ARCH-PARSE.
"""

from __future__ import annotations

import ast
import importlib.util
from collections import deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.arch_module import LOADERS, literal_import
from scripts.harness_arch import ArchConfig, Ban, under


class _Imports(ast.NodeVisitor):
    """Every module a tree imports, as (dotted name, line), in the order they appear."""

    def __init__(self, package: str | None) -> None:
        self.package = package  # the module's package, for its relative imports
        self.found: list[tuple[str, int]] = []
        self.loaders = {"__import__": "__import__"}  # names that load a module named by a string
        self.importlibs = {"importlib"}  # names bound to the importlib module

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.found.append((alias.name, node.lineno))
            if alias.name == "importlib":
                self.importlibs.add(alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = f"{'.' * node.level}{node.module or ''}"
        try:
            base = importlib.util.resolve_name(base, self.package) if node.level else base
        except ImportError:
            return  # no package to resolve it against, or more dots than it has parts
        for alias in node.names:
            name = base if alias.name == "*" else f"{base}.{alias.name}"
            self.found.append((name, node.lineno))
            if base == "importlib" and alias.name in LOADERS:
                self.loaders[alias.asname or alias.name] = alias.name

    def visit_Call(self, node: ast.Call) -> None:
        name = literal_import(node, self.loaders, self.importlibs, self.package)
        if name is not None:
            self.found.append((name, node.lineno))
        self.generic_visit(node)


def imported(tree: ast.Module, package: str | None = None) -> list[tuple[str, int]]:
    """(module, line) of each import in the tree, as ARCH-BAN judges it (the docstring above).
    `package`: the module's package, which its relative imports are resolved against; without
    it they are left out."""
    visitor = _Imports(package)
    visitor.visit(tree)
    return visitor.found


@dataclass(frozen=True)
class _Module:
    path: Path
    imports: tuple[tuple[str, int], ...]  # (module, line), as `imported` reads them


def check_bans(root: Path, arch: ArchConfig) -> list[Violation]:
    """Each import that a ban covering its module forbids, in the library and every app."""
    products = [(arch.package, arch.package_dir)] + [(app.name, app.dir) for app in arch.apps]
    violations: list[Violation] = []
    for package, folder in products:
        bans = [b for b in arch.bans if any(under(w, package) for w in b.within)]
        modules = _read(root / folder, package) if bans else {}
        for module, read in modules.items():
            for ban in bans:
                if scope := ban.scope(module):
                    violations += _check_module(root, read, ban, scope, modules)
    return sorted(violations, key=lambda v: (v.path, v.line))


def _read(folder: Path, package: str) -> dict[str, _Module]:
    """Each module of the package that parses, by its dotted name, with its imports."""
    found = {}
    for path, module, is_package in _modules(folder, package):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # ARCH-PARSE reports it
        anchor = module if is_package else module.rpartition(".")[0]
        found[module] = _Module(path, tuple(imported(tree, anchor)))
    return found


def _modules(folder: Path, package: str) -> Iterator[tuple[Path, str, bool]]:
    """Each Python file under the package's folder, with its dotted module name and whether it
    is a package's `__init__`."""
    for path in sorted(folder.rglob("*.py")):
        parts = path.relative_to(folder).with_suffix("").parts
        if "__pycache__" not in parts:
            init = parts[-1] == "__init__"
            yield path, ".".join((package, *parts[: -1 if init else None])), init


def _check_module(
    root: Path, read: _Module, ban: Ban, scope: str, modules: Mapping[str, _Module]
) -> list[Violation]:
    display = read.path.relative_to(root).as_posix()
    violations = []
    for name, line in read.imports:
        if (prefix := ban.banned(name)) is not None:
            problem = f"'{name}' is banned in '{scope}' ([[bans]]: '{prefix}')"
        elif reached := _reach(_own(name, modules), ban, modules):
            through, banned, prefix = reached
            chain = " -> ".join([*through, banned])
            problem = f"'{name}' leads to '{banned}' ({chain}), banned in '{scope}' "
            problem += f"([[bans]]: '{prefix}')"
        else:
            continue
        violations.append(Violation(display, line, "ARCH-BAN", problem, ban.fix))
    return violations


def _own(name: str, modules: Mapping[str, _Module]) -> str | None:
    """The package's own module that an imported name is, or is inside; None for another's."""
    while name and name not in modules:
        name = name.rpartition(".")[0]
    return name or None


def _reach(
    start: str | None, ban: Ban, modules: Mapping[str, _Module]
) -> tuple[list[str], str, str] | None:
    """The shortest way from the package's own module `start`, through its modules outside the
    ban, to an import the ban refuses: (those modules, the banned module, the ban's prefix).
    None when there is none, or when the ban covers `start`, whose imports are checked where
    they are written."""
    if start is None or ban.scope(start):
        return None
    came_from: dict[str, str | None] = {start: None}
    todo = deque([start])
    while todo:
        module = todo.popleft()
        for name, _ in modules[module].imports:
            if (prefix := ban.banned(name)) is not None:
                through = [module]
                while (previous := came_from[through[0]]) is not None:
                    through.insert(0, previous)
                return through, name, prefix
            target = _own(name, modules)
            if target is not None and target not in came_from and not ban.scope(target):
                came_from[target] = module
                todo.append(target)
    return None
