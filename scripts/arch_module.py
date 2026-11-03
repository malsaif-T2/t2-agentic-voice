"""The rules read inside one module of the library, for the architecture check
(scripts/check_architecture.py, which says what each enforces): ARCH-LAYER's imports, the
library's side of ARCH-PUBLIC (it never imports an app), ARCH-OWNER, ARCH-PRINT, ARCH-ENV, and
ARCH-CONSTRUCT. ModuleChecker visits a module's tree once and collects every violation.

ARCH-CONSTRUCT reads two kinds of [[restricted]] entry, each held by its `layers` and its
`files`. A class counts where a call builds it (`C(...)`, `C.model_validate(...)`, `m.C(...)`).
A name counts wherever the module's text mentions it (scripts/arch_names.py): any token that is
the name, and any literal that holds it, a docstring included; and a star import from a module
that may bind it (one of its files, or a module of its layers), which binds it unseen. No module
outside its layers and files is exempt, not even one that binds a name of the same spelling. A
name computed at run time cannot be checked statically: what the name guards checks it again at
run time.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Collection, Mapping
from pathlib import Path

from scripts._common import Violation
from scripts.arch_names import referred
from scripts.harness_arch import ArchConfig, Ownership, under

ROOT_LAYER = "<package root>"
CHANGE_RULE_FIX = (
    "If the rule itself is wrong, change it in harness.toml and ARCHITECTURE.md together, and "
    "record why in docs/design/decisions.md."
)
# ARCH-PRINT's fix when harness.toml gives `logging` no owner whose fix says how to log.
PRINT_FIX = (
    "Use the structured logger: `log = get_logger(__name__)`; `log.info('event_name', key=value)`."
)
ENV_ATTRS = frozenset({"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"})
LOADERS = ("import_module", "__import__")  # importlib's functions that load a named module
_STREAMS = frozenset({"stdout", "stderr"})


class ModuleChecker(ast.NodeVisitor):
    def __init__(
        self, arch: ArchConfig, *, layer: str, rel: str, display: str, source: str
    ) -> None:
        self.arch = arch
        self.source = source  # the module's text, which the tree was parsed from
        self.layer = layer
        self.rel = rel  # inside the package: "core/config.py"
        self.display = display
        rel_parts = rel.split("/")
        stem = Path(rel_parts[-1]).stem
        self.module_parts = [arch.package, *rel_parts[:-1], *([] if stem == "__init__" else [stem])]
        self.is_package = stem == "__init__"
        self.os_names = {"os"}  # names bound to the os module here
        self.importlib_names = {"importlib"}  # ... and to the importlib module
        # names that import a module named by a string, each with the LOADERS function it is
        self.import_functions = {"__import__": "__import__"}
        self.violations: list[Violation] = []

    def _add(self, line: int, rule: str, problem: str, fix: str) -> None:
        self.violations.append(Violation(self.display, line, rule, problem, fix))

    def visit_Module(self, node: ast.Module) -> None:
        self.generic_visit(node)
        found = referred(self.arch, self.source, node, self.display, layer=self.layer, rel=self.rel)
        self.violations += found

    # ---------------------------------------------------------------- imports

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            parts = alias.name.split(".")
            if alias.name == "os" or (parts[0] == "os" and alias.asname is None):
                self.os_names.add(alias.asname or "os")
            if alias.name == "importlib":
                self.importlib_names.add(alias.asname or "importlib")
            self._check_owner(parts[0], node.lineno)
            self._check_internal(parts, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0:
            base = (node.module or "").split(".")
            self._check_owner(base[0], node.lineno)
            if base == ["os"]:
                for alias in node.names:
                    if alias.name in ENV_ATTRS:
                        self._env_violation(node.lineno, f"os.{alias.name}")
            if base == ["importlib"]:
                for alias in node.names:
                    if alias.name in LOADERS:
                        self.import_functions[alias.asname or alias.name] = alias.name
        else:
            package = self.module_parts if self.is_package else self.module_parts[:-1]
            if node.level - 1 > len(package):
                return
            base = package[: len(package) - (node.level - 1)]
            if node.module:
                base = [*base, *node.module.split(".")]
        if any(alias.name == "*" for alias in node.names):
            self._check_star(".".join(base), node.lineno)
        # `from <package> import services` / `from .. import services`: a name may be a layer.
        if base == [self.arch.package] or node.module is None:
            for alias in node.names:
                self._check_internal([*base, alias.name], node.lineno)
        else:
            self._check_internal(base, node.lineno)
        self.generic_visit(node)

    def _check_owner(self, top: str, line: int) -> None:
        owner = self.arch.owners.get(top)
        if owner is not None and self.layer not in owner.layers:
            allowed = ", ".join(sorted(owner.layers))
            self._add(
                line,
                "ARCH-OWNER",
                f"'{top}' may only be imported in layer(s) [{allowed}], not '{self.layer}'",
                owner.fix,
            )

    def _check_internal(self, parts: list[str], line: int) -> None:
        if parts[0] in self.arch.app_names:
            self._add(
                line,
                "ARCH-PUBLIC",
                f"the library imports the app '{parts[0]}' ({'.'.join(parts)})",
                "The library never depends on an app: move what both need into the library, or "
                "let the app pass it in.",
            )
            return
        if len(parts) < 2 or parts[0] != self.arch.package or self.layer == ROOT_LAYER:
            return  # the package root is the public API: it may re-export every layer
        target = parts[1]
        if target not in self.arch.layers:
            where = "a facade" if target in self.arch.facade_names else "the package root"
            self._add(
                line,
                "ARCH-LAYER",
                f"layer '{self.layer}' imports '{'.'.join(parts)}' from {where}",
                "Import it from the layer that defines it; the package root and the facades "
                "only re-export the public API for apps.",
            )
            return
        if target == self.layer:
            return
        for rule in self.arch.subpackages:
            if f"{self.rel}/".startswith(f"{rule.path}/") and target in rule.may_not_import:
                self._add(
                    line,
                    "ARCH-LAYER",
                    f"{rule.path}/ may not import layer '{target}' ({'.'.join(parts)})",
                    f"{rule.fix} {CHANGE_RULE_FIX}",
                )
        allowed = self.arch.layers.get(self.layer, frozenset())
        if target not in allowed:
            allowed_text = ", ".join(sorted(allowed)) or "no other layer"
            self._add(
                line,
                "ARCH-LAYER",
                f"layer '{self.layer}' imports layer '{target}' ({'.'.join(parts)}); "
                f"'{self.layer}' may import: {allowed_text}",
                "Move the shared code down into a layer both may import (often core/), or "
                "pass the dependency in from a higher layer. " + CHANGE_RULE_FIX,
            )

    # ---------------------------------------------------------------- calls & attributes

    def visit_Call(self, node: ast.Call) -> None:
        imported = self._imported_by_name(node)
        if imported is not None:
            self._check_owner(imported[0], node.lineno)
            self._check_internal(imported, node.lineno)
        if _writes_output(node.func) and self.rel not in self.arch.output_allowed_files:
            self._add(
                node.lineno,
                "ARCH-PRINT",
                "print() or a direct sys.stdout/sys.stderr write in application code",
                _owners_fix(self.arch, "logging", PRINT_FIX),
            )
        name = _constructed_class(node.func, self.arch.restricted.keys())
        restriction = self.arch.restricted.get(name) if name else None
        if restriction is not None and not restriction.allows(self.layer, self.rel):
            self._add(
                node.lineno,
                "ARCH-CONSTRUCT",
                f"'{name}' constructed in layer '{self.layer}'",
                restriction.fix,
            )
        self.generic_visit(node)

    def _imported_by_name(self, node: ast.Call) -> list[str] | None:
        """The module the call loads by a literal name, split on dots (`literal_import`)."""
        package = self.module_parts if self.is_package else self.module_parts[:-1]
        name = literal_import(node, self.import_functions, self.importlib_names, ".".join(package))
        return name.split(".") if name is not None else None

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self.os_names
            and node.attr in ENV_ATTRS
        ):
            self._env_violation(node.lineno, f"os.{node.attr}")
        self.generic_visit(node)

    def _check_star(self, module: str, line: int) -> None:
        """ARCH-CONSTRUCT for `from <module> import *`, when `module` may bind a [[restricted]]
        name this module may not mention: the import binds it with no mention."""
        for name, restriction in self.arch.restricted_names.items():
            if not restriction.allows(self.layer, self.rel) and self._binds(module, restriction):
                problem = f"'*' imported from '{module}', which may bind '{name}', in layer "
                self._add(line, "ARCH-CONSTRUCT", f"{problem}'{self.layer}'", restriction.fix)

    def _binds(self, module: str, restriction: Ownership) -> bool:
        """Whether `module` is one of the restriction's files, or a module of its layers."""
        package = self.arch.package
        if any(module == _module_name(package, path) for path in restriction.files):
            return True
        return any(under(module, f"{package}.{layer}") for layer in restriction.layers)

    def _env_violation(self, line: int, what: str) -> None:
        if self.rel in self.arch.env_allowed_files:
            return
        allowed = ", ".join(sorted(self.arch.env_allowed_files)) or "no module"
        fix = f"Read the setting in {allowed}, and pass its value in."
        self._add(
            line,
            "ARCH-ENV",
            f"{what} used outside {allowed}",
            _owners_fix(self.arch, "pydantic_settings", fix),
        )


def literal_import(
    node: ast.Call,
    functions: Mapping[str, str],
    importlibs: Collection[str],
    package: str | None = None,
) -> str | None:
    """The module a call loads by a literal name, given by position or as `name=`:
    `importlib.import_module("a.b")`, or a relative `import_module(".b", "a")` resolved against
    its literal anchor; `__import__("a.b")` or `importlib.__import__("a.b")`, and one with a
    literal `level` above 0 resolved against `package`, the calling module's own package. A
    computed name, or a relative one with no literal anchor, cannot be checked statically.
    `functions`: each name bound here to one of LOADERS, with the one it is (`__import__`
    itself; `load` after `from importlib import import_module as load`); `importlibs`: the names
    bound to the importlib module."""
    func = node.func
    if isinstance(func, ast.Name):
        loader = functions.get(func.id)
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        loader = func.attr if func.value.id in importlibs and func.attr in LOADERS else None
    else:
        loader = None
    name = _literal(_argument(node, 0, "name"))
    if loader is None or not isinstance(name, str) or not name:
        return None
    anchor: object = package
    if loader == "__import__":
        given = _argument(node, 4, "level")
        level = 0 if given is None else _literal(given)
        if name.startswith(".") or type(level) is not int or level < 0:
            return None
        name = "." * level + name
    else:
        anchor = _literal(_argument(node, 1, "package"))
    if not name.startswith("."):
        return name
    try:
        return importlib.util.resolve_name(name, anchor) if isinstance(anchor, str) else None
    except ImportError:
        return None  # an empty anchor, or more dots than it has parts


def _argument(node: ast.Call, position: int, keyword: str) -> ast.expr | None:
    """The call's argument at `position`, or given as `keyword=`; None when it has none."""
    if len(node.args) > position:
        return node.args[position]
    return next((k.value for k in node.keywords if k.arg == keyword), None)


def _literal(node: ast.expr | None) -> object:
    """A literal argument's value; None when it is missing or computed."""
    return node.value if isinstance(node, ast.Constant) else None


def _owners_fix(arch: ArchConfig, module: str, fallback: str) -> str:
    """The fix harness.toml gives for importing `module` outside its owner: it already says how
    to log, or how to add a setting, so ARCH-PRINT and ARCH-ENV say it in the same words."""
    owner = arch.owners.get(module)
    return owner.fix if owner is not None else fallback


def _writes_output(func: ast.expr) -> bool:
    """`print(...)`, or `sys.stdout.write(...)` and the like."""
    if isinstance(func, ast.Name):
        return func.id == "print"
    return (
        isinstance(func, ast.Attribute)
        and func.attr in ("write", "writelines")
        and isinstance(func.value, ast.Attribute)
        and func.value.attr in _STREAMS
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "sys"
    )


def _module_name(package: str, path: str) -> str:
    """The dotted name of the module at `path` inside `package`: "core/identity.py" is
    "<package>.core.identity", and "core/__init__.py" is "<package>.core"."""
    parts = Path(path).with_suffix("").parts
    return ".".join([package, *(parts[:-1] if parts[-1] == "__init__" else parts)])


def _constructed_class(func: ast.expr, names: Collection[str]) -> str | None:
    """Name of a restricted class if `func(...)` constructs or validates it."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        if func.attr in names:
            return func.attr
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id in names:
            return owner.id
        if isinstance(owner, ast.Attribute) and owner.attr in names:
            return owner.attr
    return None
