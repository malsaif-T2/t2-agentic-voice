"""The harness's settings: harness.toml at the repository root, read once into typed values.

Every check takes a HarnessConfig (their tests pass small ones of their own), so a project
changes its rules by editing harness.toml, never the checks. A mistake in the file, such as a
layer that imports an unknown layer or a cycle in the layer graph, is a HARNESS-CONFIG
violation with a FIX line, like any other.
"""

from __future__ import annotations

import keyword
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._common import Violation, report
from scripts.harness_toml import CONFIG_FILE, FIX, RULE, Lines, Table, tables

_PACKAGE = re.compile(r"^[a-z_][a-z0-9_]*$")
# The tables harness.toml may hold; [tool.*] holds other tools' settings (coverage.py's).
_TABLES = frozenset(
    {"package", "layers", "owners", "restricted", "subpackages", "apps", "rules", "modules"}
    | {"docs", "plans", "references", "gc", "quality", "tool"}
)
WEIGHTS = ("coverage", "size", "suppressions", "duplication", "docstrings")


class HarnessConfigError(Exception):
    """harness.toml is missing or invalid; `violations` say where, and how to fix it."""

    def __init__(self, violations: list[Violation]) -> None:
        super().__init__("\n".join(map(str, violations)))
        self.violations = violations


@dataclass(frozen=True)
class Ownership:
    """Who may import a library (ARCH-OWNER) or construct a class (ARCH-CONSTRUCT)."""

    layers: frozenset[str]
    fix: str


@dataclass(frozen=True)
class SubpackageRule:
    path: str  # inside the package, starting with its layer: "services/reports"
    may_not_import: frozenset[str]
    fix: str


@dataclass(frozen=True)
class AppRule:
    """A package built on the library (ARCH-PUBLIC): it imports only the library's public
    modules and no other app, and the library never imports it."""

    name: str
    root: str  # the folder that holds it, from the repository root: "apps/x/src"

    @property
    def dir(self) -> str:
        return f"{self.root}/{self.name}"


@dataclass(frozen=True)
class ArchConfig:
    package: str
    package_root: str  # the folder that holds the package, from the repository root
    public: frozenset[str]  # the modules an app may import: "app", "app.testing"
    facades: frozenset[str]  # public modules at the package root, re-exports only: "app.ports"
    banned_words: tuple[str, ...]  # never in the library's src/, in any case (ARCH-WORDS)
    apps: tuple[AppRule, ...]
    layers: Mapping[str, frozenset[str]]  # layer -> the other layers it may import
    owners: Mapping[str, Ownership]  # top-level module -> the layers that may import it
    restricted: Mapping[str, Ownership]  # class name -> the layers that may construct it
    subpackages: tuple[SubpackageRule, ...]
    env_allowed_files: frozenset[str]
    output_allowed_files: frozenset[str]
    architecture_doc: str  # "" when ARCH-DOC is off
    max_module_lines: int
    support_dirs: tuple[str, ...]

    @property
    def app_names(self) -> frozenset[str]:
        return frozenset(app.name for app in self.apps)

    def is_public(self, module: str) -> bool:
        """Whether an app may import `module`: a public module, or one inside a public
        subpackage. The package root being public makes only the root public."""
        return module in self.public or any(
            p != self.package and module.startswith(f"{p}.") for p in self.public
        )

    @property
    def facade_names(self) -> frozenset[str]:
        """The facades' own names, as their files are named under the package: "ports"."""
        return frozenset(f.removeprefix(f"{self.package}.") for f in self.facades)


@dataclass(frozen=True)
class DocsConfig:
    entry: str
    max_entry_lines: int
    required: tuple[str, ...]
    historical: tuple[str, ...]
    code_dirs: tuple[str, ...]
    code_exempt: frozenset[str]
    placeholders_allowed_in: tuple[str, ...]


@dataclass(frozen=True)
class PlansConfig:
    roadmap: str
    active: str
    completed: str
    sections: tuple[str, ...]


@dataclass(frozen=True)
class ReferencesConfig:
    decisions: str
    tech_debt: str
    golden_principles: str
    invariants: str


@dataclass(frozen=True)
class GcConfig:
    due_after_commits: int
    min_tokens: int
    size_watch: int
    path_bases: tuple[str, ...]
    path_ignored: tuple[str, ...]
    hooks: frozenset[str]
    foreign_names: frozenset[str]
    name_files: tuple[str, ...]


@dataclass(frozen=True)
class QualityConfig:
    doc: str
    weights: Mapping[str, int]
    suppressions_floor: float
    duplication_floor: int


@dataclass(frozen=True)
class HarnessConfig:
    arch: ArchConfig
    docs: DocsConfig
    plans: PlansConfig
    references: ReferencesConfig
    gc: GcConfig
    quality: QualityConfig

    @property
    def package_dir(self) -> str:
        """The package's folder, from the repository root: `<root>/<name>`."""
        return f"{self.arch.package_root}/{self.arch.package}"

    @property
    def product_dirs(self) -> tuple[str, ...]:
        """The library's folder and every app's, from the repository root."""
        return (self.package_dir, *(app.dir for app in self.arch.apps))


def load_config(root: Path) -> HarnessConfig:
    """harness.toml under `root`, parsed and checked; HarnessConfigError lists every problem."""
    path = root / CONFIG_FILE
    if not path.is_file():
        fix = "Restore harness.toml at the repository root (see git history or the kit)."
        raise HarnessConfigError([Violation(CONFIG_FILE, 1, RULE, "harness.toml is missing", fix)])
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        line = getattr(error, "lineno", 1)
        raise HarnessConfigError([Violation(CONFIG_FILE, line, RULE, str(error), FIX)]) from None
    lines = Lines(text)
    config = parse_config(data, lines)
    if missing := _missing_facades(root, config, lines):
        raise HarnessConfigError(missing)
    return config


def _missing_facades(root: Path, config: HarnessConfig, lines: Lines) -> list[Violation]:
    """A facade [package] facades names whose module file does not exist."""
    found = []
    for name in sorted(config.arch.facade_names):
        path = f"{config.package_dir}/{name}.py"
        if not (root / path).is_file():
            problem = f"facade '{config.arch.package}.{name}' has no module: {path} is missing"
            fix = f"Create {path} (a docstring, imports and `__all__`), or remove it from facades."
            found.append(Violation(CONFIG_FILE, lines.of("package", "facades"), RULE, problem, fix))
    return found


def parse_config(data: dict[str, Any], lines: Lines) -> HarnessConfig:
    problems: list[Violation] = []
    for name in sorted(set(data) - set(_TABLES)):
        problem = f"unknown table [{name}]"
        fix = "Remove it, or put another tool's settings under [tool.<name>]."
        problems.append(Violation(CONFIG_FILE, lines.of(name), RULE, problem, fix))
    arch = _arch(data, lines, problems)
    docs = Table("docs", data.get("docs"), lines, problems)
    docs_config = DocsConfig(
        entry=docs.string("entry"),
        max_entry_lines=docs.integer("max_entry_lines"),
        required=docs.strings("required"),
        historical=docs.strings("historical"),
        code_dirs=docs.strings("code_dirs"),
        code_exempt=frozenset(docs.strings("code_exempt")),
        placeholders_allowed_in=docs.strings("placeholders_allowed_in"),
    )
    plans = Table("plans", data.get("plans"), lines, problems)
    plans_config = PlansConfig(
        roadmap=plans.string("roadmap"),
        active=plans.string("active"),
        completed=plans.string("completed"),
        sections=plans.strings("sections"),
    )
    refs = Table("references", data.get("references"), lines, problems)
    references = ReferencesConfig(
        *(refs.string(k, empty=True) for k in ReferencesConfig.__dataclass_fields__)
    )
    gc = Table("gc", data.get("gc"), lines, problems)
    gc_config = GcConfig(
        due_after_commits=gc.integer("due_after_commits"),
        min_tokens=gc.integer("min_tokens"),
        size_watch=gc.integer("size_watch"),
        path_bases=gc.strings("path_bases", blank_items=True),
        path_ignored=gc.strings("path_ignored"),
        hooks=frozenset(gc.strings("hooks")),
        foreign_names=frozenset(gc.strings("foreign_names")),
        name_files=gc.strings("name_files"),
    )
    quality = Table("quality", data.get("quality"), lines, problems)
    weights = quality.table("weights")
    quality_config = QualityConfig(
        doc=quality.string("doc"),
        weights={k: weights.integer(k, minimum=0) for k in WEIGHTS},
        suppressions_floor=quality.number("suppressions_floor"),
        duplication_floor=quality.integer("duplication_floor"),
    )
    for table in (docs, plans, refs, gc, quality, weights):
        table.finish()
    if problems:
        raise HarnessConfigError(problems)
    return HarnessConfig(arch, docs_config, plans_config, references, gc_config, quality_config)


def _arch(data: dict[str, Any], lines: Lines, problems: list[Violation]) -> ArchConfig:
    package = Table("package", data.get("package"), lines, problems)
    name = package.string("name")
    if name and (not _PACKAGE.match(name) or keyword.iskeyword(name)):
        package.problem("name", f"'{name}' is not a Python package name")
    public = frozenset(package.strings("public"))
    for module in sorted(m for m in public if m.split(".")[0] != name):
        package.problem("public", f"public module '{module}' is not inside package '{name}'")
    facades = frozenset(package.strings("facades"))
    banned_words = package.strings("banned_words")
    apps = _apps(tables(data, "apps", lines, problems), name)
    layers_table = Table("layers", data.get("layers"), lines, problems)
    layers = {key: frozenset(layers_table.strings(key)) for key in layers_table.data}
    for facade in sorted(facades):
        _check_facade(package, facade, name, public, set(layers))
    if not layers:
        layers_table.problem(None, "[layers] names no layer")
    for layer, imports in layers.items():
        if not _PACKAGE.match(layer):
            layers_table.problem(layer, f"layer '{layer}' is not a folder name for a package")
        for unknown in sorted(imports - set(layers)):
            layers_table.problem(layer, f"layer '{layer}' may import '{unknown}', not a layer")
    if cycle := _cycle(layers):
        layers_table.problem(cycle[0], f"the layer graph has a cycle: {' -> '.join(cycle)}")
    owners = _owned(tables(data, "owners", lines, problems), "modules", set(layers))
    restricted = _owned(tables(data, "restricted", lines, problems), "classes", set(layers))
    subpackages = []
    for table in tables(data, "subpackages", lines, problems):
        path, forbidden = table.string("path"), frozenset(table.strings("may_not_import"))
        if path.split("/")[0] not in layers:
            table.problem("path", f"subpackage '{path}' does not start with a layer's folder")
        for unknown in sorted(forbidden - set(layers)):
            table.problem("may_not_import", f"'{unknown}' is not a layer")
        subpackages.append(SubpackageRule(path, forbidden, table.string("fix")))
        table.finish()
    rules = Table("rules", data.get("rules"), lines, problems)
    modules = Table("modules", data.get("modules"), lines, problems)
    arch = ArchConfig(
        package=name,
        package_root=package.string("root"),
        public=public,
        facades=facades,
        banned_words=banned_words,
        apps=apps,
        layers=layers,
        owners=owners,
        restricted=restricted,
        subpackages=tuple(subpackages),
        env_allowed_files=frozenset(rules.strings("env_allowed_files")),
        output_allowed_files=frozenset(rules.strings("output_allowed_files")),
        architecture_doc=rules.string("architecture_doc", empty=True),
        max_module_lines=modules.integer("max_lines"),
        support_dirs=modules.strings("support_dirs"),
    )
    for table in (package, rules, modules):
        table.finish()
    return arch


def _check_facade(
    package: Table, facade: str, name: str, public: frozenset[str], layers: set[str]
) -> None:
    """A facade sits directly under the package root, is public, and is not named as a layer."""
    parts = facade.split(".")
    if len(parts) != 2 or parts[0] != name or not _PACKAGE.match(parts[1]):
        package.problem("facades", f"facade '{facade}' is not a module directly under '{name}'")
    elif parts[1] in layers:
        package.problem("facades", f"facade '{facade}' has the name of a layer")
    if facade not in public:
        package.problem("facades", f"facade '{facade}' is not in [package] public")


def _apps(groups: list[Table], package: str) -> tuple[AppRule, ...]:
    """The [[apps]] tables: each a package name, distinct from the library's and each other's."""
    found: list[AppRule] = []
    for table in groups:
        name = table.string("name")
        if name and (not _PACKAGE.match(name) or keyword.iskeyword(name)):
            table.problem("name", f"'{name}' is not a Python package name")
        elif name in {package, *(app.name for app in found)}:
            table.problem("name", f"'{name}' is already the library's or another app's name")
        found.append(AppRule(name, table.string("root")))
        table.finish()
    return tuple(found)


def _owned(groups: list[Table], key: str, layers: set[str]) -> dict[str, Ownership]:
    """name -> Ownership, from [[owners]] (key "modules") or [[restricted]] (key "classes")."""
    found: dict[str, Ownership] = {}
    for table in groups:
        names = table.strings(key, non_empty=True)
        owners = frozenset(table.strings("layers", non_empty=True))
        for unknown in sorted(owners - layers):
            table.problem("layers", f"[[{table.name}]] names '{unknown}', not a layer")
        ownership = Ownership(owners, table.string("fix"))
        for name in names:
            if name in found:
                table.problem(key, f"'{name}' is listed in two [[{table.name}]] tables")
            found[name] = ownership
        table.finish()
    return found


def _cycle(graph: Mapping[str, frozenset[str]]) -> list[str]:
    """One cycle in the graph, as a path that ends where it starts; empty if there is none."""
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str]:
        if node in path:
            return [*path[path.index(node) :], node]
        if node in done or node not in graph:
            return []
        for target in sorted(graph[node] - {node}):
            if found := visit(target, [*path, node]):
                return found
        done.add(node)
        return []

    for start in graph:
        if found := visit(start, []):
            return found
    return []


Check = Callable[[Path, HarnessConfig], tuple[list[Violation], int]]


def run_check(name: str, root: Path, check: Check) -> int:
    """A check's `main`: load the config, run the check, print the outcome, return the code."""
    try:
        config = load_config(root)
    except HarnessConfigError as error:
        return report(name, error.violations, 1)
    violations, checked = check(root, config)
    return report(name, violations, checked)
