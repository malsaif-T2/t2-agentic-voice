"""ARCH-DEPS, for the architecture check (scripts/check_architecture.py): every outside module
the code imports is declared by the project the code belongs to, never borrowed from another
package's dependencies (a library that arrives only under another can be dropped by it).

- The library's src/ and each app's import only what that member's pyproject.toml declares in
  [project] dependencies: the nearest pyproject.toml at or above its root ([package] root,
  [[apps]] root).
- scripts/ and tests/ ([modules] support_dirs) run from the repository root, which depends on
  every member, so they import what the root's [project] dependencies or `dev` group declares,
  or what any member declares.

A module maps to the distributions that install it through the installed environment
(importlib.metadata.packages_distributions), and a member's package to the member's own
[project] name. The standard library, `__future__`, relative imports, the support folders' own
packages, and a member's own package need no declaration. A module that no installed
distribution provides is reported too: nothing declares it. Import statements are read
anywhere in a module (inside a function too); a module loaded by a computed name is not.
"""

from __future__ import annotations

import ast
import importlib.metadata
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.harness_arch import ArchConfig

_STDLIB = sys.stdlib_module_names | {"__future__"}
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalized(name: str) -> str:
    """A distribution's name as packaging compares names: `Shop_Tools` is `shop-tools`."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Project:
    pyproject: str  # from the repository root
    name: str  # its [project] name, normalized
    declared: frozenset[str]  # the distributions it depends on, normalized


def check_deps(
    root: Path, arch: ArchConfig, distributions: Mapping[str, Sequence[str]] | None = None
) -> list[Violation]:
    """Each import of a module that the importing code's project does not declare.
    `distributions`: module -> the distributions that install it (the environment's when None)."""
    found = importlib.metadata.packages_distributions() if distributions is None else distributions
    products = [(arch.package, arch.package_root, arch.package_dir)]
    products += [(app.name, app.root, app.dir) for app in arch.apps]
    members = {name: p for name, src, _ in products if (p := _project(root, src)) is not None}
    own = {name: project.name for name, project in members.items()}
    violations = []
    for name, _, folder in products:
        if (project := members.get(name)) is not None:
            allowed = project.declared | {project.name}
            violations += _undeclared(root, [folder], allowed, own, found, project)
    workspace = _project(root, "")
    every = [
        m.declared | {m.name} for m in [*members.values(), *([workspace] if workspace else [])]
    ]
    allowed = _dev_group(root).union(*every)
    supported = {**own, **dict.fromkeys(arch.support_dirs, "")}
    violations += _undeclared(root, arch.support_dirs, allowed, supported, found, None)
    return violations


def _undeclared(
    root: Path,
    folders: Sequence[str],
    allowed: frozenset[str],
    own: Mapping[str, str],
    distributions: Mapping[str, Sequence[str]],
    project: Project | None,
) -> list[Violation]:
    """The imports under `folders` that no distribution in `allowed` provides. `own`: the
    repository's packages -> the member that holds them ("" for a support folder's)."""
    violations = []
    files = sorted(p for d in folders for p in (root / d).rglob("*.py"))
    for path in (p for p in files if "__pycache__" not in p.parts):
        display = path.relative_to(root).as_posix()
        for top, line in _imports(path.read_text(encoding="utf-8")):
            if top in _STDLIB or (top in own and (not own[top] or own[top] in allowed)):
                continue
            provided = [own[top]] if top in own else sorted(set(distributions.get(top, ())))
            if not {normalized(d) for d in provided} & allowed:
                violations.append(_violation(display, line, top, provided, project))
    return violations


def _violation(
    display: str, line: int, top: str, provided: Sequence[str], project: Project | None
) -> Violation:
    if not provided:
        problem = f"'{top}' is installed by no distribution, so nothing declares it"
        dist = "<its distribution>"
    else:
        which = (
            f"which {project.pyproject} does not declare"
            if project
            else "which no member and not the root (its dependencies, its `dev` group) declares"
        )
        problem = f"'{top}' comes from {', '.join(provided)}, {which}"
        dist = provided[0] if len(provided) == 1 else f"<one of {', '.join(provided)}>"
    command = f"uv add --package {project.name} {dist}" if project else f"uv add --dev {dist}"
    fix = (
        f"Declare it in the project whose code imports it: `{command}`; never pip or edit uv.lock."
    )
    return Violation(display, line, "ARCH-DEPS", problem, fix)


def _imports(source: str) -> Iterable[tuple[str, int]]:
    """(top-level module, line) of the first absolute import of each module in the source."""
    seen: dict[str, int] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            seen[top] = min(seen.get(top, node.lineno), node.lineno)
    return sorted(seen.items(), key=lambda item: item[1])


def _project(root: Path, folder: str) -> Project | None:
    """The project of the nearest pyproject.toml at or above `folder`, inside the repository."""
    here = (root / folder).resolve()
    top = root.resolve()
    while not (here / "pyproject.toml").is_file():
        if here == top or top not in here.parents:
            return None
        here = here.parent
    path = here / "pyproject.toml"
    project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    declared = _names(project.get("dependencies", []))
    return Project(path.relative_to(top).as_posix(), normalized(project.get("name", "")), declared)


def _dev_group(root: Path) -> frozenset[str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return frozenset()
    groups = tomllib.loads(path.read_text(encoding="utf-8")).get("dependency-groups", {})
    return _names(groups.get("dev", []))


def _names(requirements: Iterable[object]) -> frozenset[str]:
    """The distributions that requirement strings name (an included group is not a string)."""
    found = (_REQUIREMENT.match(r) for r in requirements if isinstance(r, str))
    return frozenset(normalized(match.group(1)) for match in found if match)
