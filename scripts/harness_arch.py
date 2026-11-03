"""harness.toml's architecture tables, for scripts/harness_config.py: [package], [layers],
[[owners]], [[restricted]], [[bans]], [[apps]], [[subpackages]], [rules], and [modules], read
into an ArchConfig that the architecture check and its helpers apply.

Each problem is a HARNESS-CONFIG violation with its line (scripts/harness_toml.py), so a layer
that imports an unknown layer, a cycle in the layer graph, or a facade outside the public API is
reported with every other mistake in the file.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._common import Violation
from scripts.harness_toml import CONFIG_FILE, RULE, Lines, Table, tables

_PACKAGE = re.compile(r"^[a-z_][a-z0-9_]*$")
_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def under(name: str, prefix: str) -> bool:
    """Whether the dotted `name` is `prefix` or a module inside it: `a.b.c` is under `a.b`,
    `a.bc` is not."""
    return name == prefix or name.startswith(f"{prefix}.")


@dataclass(frozen=True)
class Ownership:
    """Who may import a library (ARCH-OWNER), or construct a class or refer to a name
    (ARCH-CONSTRUCT): every module of `layers`, and for [[restricted]] each module of `files`
    too, a path inside the package ("core/identity.py")."""

    layers: frozenset[str]
    fix: str
    files: frozenset[str] = frozenset()

    def allows(self, layer: str, rel: str) -> bool:
        """Whether the module `rel` ("voice/session/call.py"), in `layer`, is one of these."""
        return layer in self.layers or rel in self.files


@dataclass(frozen=True)
class Ban:
    """Modules the code `within` covers never imports (ARCH-BAN): each of `modules` with every
    module under it, but each of `allowed` with every module under it."""

    modules: tuple[str, ...]  # "pipecat.services"
    allowed: tuple[str, ...]  # "pipecat.services.stt_service"
    within: tuple[str, ...]  # module prefixes of the library or an app: "app.voice.session"
    fix: str

    def scope(self, module: str) -> str | None:
        """The entry of `within` that covers the importing `module`, if one does."""
        return next((w for w in self.within if under(module, w)), None)

    def banned(self, name: str) -> str | None:
        """The banned module that the imported `name` falls under, unless it is allowed."""
        if any(under(name, a) for a in self.allowed):
            return None
        return next((m for m in self.modules if under(name, m)), None)


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
    restricted: Mapping[str, Ownership]  # class name -> the modules that may construct it
    restricted_names: Mapping[str, Ownership]  # name -> the only modules that may refer to it
    bans: tuple[Ban, ...]
    subpackages: tuple[SubpackageRule, ...]
    env_allowed_files: frozenset[str]
    output_allowed_files: frozenset[str]
    architecture_doc: str  # "" when ARCH-DOC is off
    max_module_lines: int
    support_dirs: tuple[str, ...]

    @property
    def package_dir(self) -> str:
        """The package's folder, from the repository root: `<root>/<name>`."""
        return f"{self.package_root}/{self.package}"

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


def missing_facades(root: Path, arch: ArchConfig, lines: Lines) -> list[Violation]:
    """A facade [package] facades names whose module file does not exist."""
    found = []
    for name in sorted(arch.facade_names):
        path = f"{arch.package_dir}/{name}.py"
        if not (root / path).is_file():
            problem = f"facade '{arch.package}.{name}' has no module: {path} is missing"
            fix = f"Create {path} (a docstring, imports and `__all__`), or remove it from facades."
            found.append(Violation(CONFIG_FILE, lines.of("package", "facades"), RULE, problem, fix))
    return found


def missing_scopes(root: Path, arch: ArchConfig, lines: Lines) -> list[Violation]:
    """A [[bans]] `within` that names no package (a folder with `__init__.py`) or module of the
    library or an app: renamed or moved, it would leave its ban guarding nothing."""
    folders = {arch.package: arch.package_root} | {app.name: app.root for app in arch.apps}
    found = []
    for index, ban in enumerate(arch.bans):
        for name in (w for w in ban.within if w.split(".")[0] in folders):
            path = Path(folders[name.split(".")[0]], *name.split("."))
            if not ((root / path / "__init__.py").is_file() or (root / f"{path}.py").is_file()):
                shown = path.as_posix()
                problem = (
                    f"[[bans]] within '{name}' names no package or module: neither "
                    f"{shown}/__init__.py nor {shown}.py exists"
                )
                fix = (
                    "Name the package or module the ban covers as it is now (was it renamed or "
                    "moved?), or remove the entry from `within`."
                )
                line = lines.of("bans", "within", index)
                found.append(Violation(CONFIG_FILE, line, RULE, problem, fix))
    return found


def parse_arch(data: dict[str, Any], lines: Lines, problems: list[Violation]) -> ArchConfig:
    package = Table("package", data.get("package"), lines, problems)
    name = _package_name(package)
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
    restricted, restricted_names = _restricted(
        tables(data, "restricted", lines, problems), set(layers)
    )
    places = {name: set(layers) | {f.removeprefix(f"{name}.") for f in facades}}
    places |= {app.name: set() for app in apps if app.name}
    bans = tuple(_ban(table, places) for table in tables(data, "bans", lines, problems))
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
        restricted_names=restricted_names,
        bans=bans,
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


def _package_name(table: Table) -> str:
    """The table's `name`, which must be a Python package's name: [package] and each [[apps]]."""
    name = table.string("name")
    if name and (not _PACKAGE.match(name) or keyword.iskeyword(name)):
        table.problem("name", f"'{name}' is not a Python package name")
    return name


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
        before = len(table.problems)
        name = _package_name(table)
        valid = len(table.problems) == before  # a name that is no package name is not a clash
        if valid and name in {package, *(a.name for a in found)}:
            table.problem("name", f"'{name}' is already the library's or another app's name")
        found.append(AppRule(name, table.string("root")))
        table.finish()
    return tuple(found)


def _restricted(
    groups: list[Table], layers: set[str]
) -> tuple[dict[str, Ownership], dict[str, Ownership]]:
    """[[restricted]]'s classes (a call that builds one counts) and its names (every mention
    counts): each table lists `classes` or `names`, not both, and the `layers` and the `files`
    whose modules may, one of the two empty at most."""
    for table in (t for t in groups if {"classes", "names"} <= t.data.keys()):
        table.problem("names", "[[restricted]] lists `classes` or `names`, not both")
        table.seen.add("classes")
    classes = _owned([t for t in groups if "names" not in t.data], "classes", layers, files=True)
    names = _owned([t for t in groups if "names" in t.data], "names", layers, files=True)
    return classes, names


def _owned(
    groups: list[Table], key: str, layers: set[str], *, files: bool = False
) -> dict[str, Ownership]:
    """name -> Ownership, from [[owners]] (key "modules") or [[restricted]] (key "classes" or
    "names", with `files`: modules of the library, each a path inside the package)."""
    found: dict[str, Ownership] = {}
    for table in groups:
        names = table.strings(key, non_empty=True)
        owners = frozenset(table.strings("layers", non_empty=not files))
        modules = frozenset(table.strings("files")) if files else frozenset()
        if files and not owners | modules and {"layers", "files"} <= table.data.keys():
            table.problem("layers", f"[[{table.name}]] names no layer and no file")
        for unknown in sorted(owners - layers):
            table.problem("layers", f"[[{table.name}]] names '{unknown}', not a layer")
        for path in sorted(m for m in modules if not _module_path(m, layers)):
            problem = f"[[{table.name}]] files: '{path}' is not a module of a layer"
            table.problem("files", f"{problem} ('<layer>/<name>.py', inside the package)")
        ownership = Ownership(owners, table.string("fix"), modules)
        for name in names:
            if name in found:
                table.problem(key, f"'{name}' is listed in two [[{table.name}]] tables")
            found[name] = ownership
        table.finish()
    return found


def _module_path(path: str, layers: set[str]) -> bool:
    """Whether `path` names a module of one of `layers`, inside the package: "core/identity.py"."""
    parts = path.split("/")
    return (
        len(parts) > 1
        and parts[0] in layers
        and path.endswith(".py")
        and all(_PACKAGE.match(p) for p in [*parts[:-1], parts[-1].removesuffix(".py")])
    )


def _ban(table: Table, places: Mapping[str, set[str]]) -> Ban:
    """One [[bans]] table. `places`: the library's package and each app's, each with the names
    a module directly under it may have in `within` (the library's layers and facades; any for
    an app)."""
    modules, allowed = table.strings("modules", non_empty=True), table.strings("allowed")
    within = table.strings("within", non_empty=True)
    for key, names in (("modules", modules), ("allowed", allowed), ("within", within)):
        for name in (n for n in names if not _MODULE.match(n)):
            table.problem(key, f"[[bans]] {key}: '{name}' is not a dotted module name")
    for name in (a for a in allowed if not any(under(a, m) and a != m for m in modules)):
        table.problem("allowed", f"[[bans]] allows '{name}', which is inside no banned module")
    for name in within:
        parts = name.split(".")
        if parts[0] not in places:
            known = ", ".join(sorted(places))
            problem = f"[[bans]] within '{name}': not the library or an app (one of: {known})"
            table.problem("within", problem)
        elif len(parts) > 1 and places[parts[0]] and parts[1] not in places[parts[0]]:
            problem = f"[[bans]] within '{name}': '{parts[1]}' is no layer or facade of the library"
            table.problem("within", problem)
    ban = Ban(modules, allowed, within, table.string("fix"))
    table.finish()
    return ban


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
