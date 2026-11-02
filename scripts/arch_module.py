"""The rules read inside one module of the library, for the architecture check
(scripts/check_architecture.py, which says what each enforces): ARCH-LAYER's imports, the
library's side of ARCH-PUBLIC (it never imports an app), ARCH-OWNER, ARCH-PRINT, ARCH-ENV, and
ARCH-CONSTRUCT. ModuleChecker visits a module's tree once and collects every violation.
"""

from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path

from scripts._common import Violation
from scripts.harness_arch import ArchConfig

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
_STREAMS = frozenset({"stdout", "stderr"})


class ModuleChecker(ast.NodeVisitor):
    def __init__(self, arch: ArchConfig, *, layer: str, rel: str, display: str) -> None:
        self.arch = arch
        self.layer = layer
        self.rel = rel  # inside the package: "core/config.py"
        self.display = display
        rel_parts = rel.split("/")
        stem = Path(rel_parts[-1]).stem
        self.module_parts = [arch.package, *rel_parts[:-1], *([] if stem == "__init__" else [stem])]
        self.is_package = stem == "__init__"
        self.os_names = {"os"}  # names bound to the os module here
        self.importlib_names = {"importlib"}  # ... and to the importlib module
        self.import_functions = {"__import__"}  # names that import a module named by a string
        self.violations: list[Violation] = []

    def _add(self, line: int, rule: str, problem: str, fix: str) -> None:
        self.violations.append(Violation(self.display, line, rule, problem, fix))

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
                    if alias.name == "import_module":
                        self.import_functions.add(alias.asname or alias.name)
        else:
            package = self.module_parts if self.is_package else self.module_parts[:-1]
            if node.level - 1 > len(package):
                return
            base = package[: len(package) - (node.level - 1)]
            if node.module:
                base = [*base, *node.module.split(".")]
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
        if restriction is not None and self.layer not in restriction.layers:
            self._add(
                node.lineno,
                "ARCH-CONSTRUCT",
                f"'{name}' constructed in layer '{self.layer}'",
                restriction.fix,
            )
        self.generic_visit(node)

    def _imported_by_name(self, node: ast.Call) -> list[str] | None:
        """The module the call loads by a literal name, split on dots (`literal_import`)."""
        name = literal_import(node, self.import_functions, self.importlib_names)
        return name.split(".") if name is not None else None

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self.os_names
            and node.attr in ENV_ATTRS
        ):
            self._env_violation(node.lineno, f"os.{node.attr}")
        self.generic_visit(node)

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
    node: ast.Call, functions: Collection[str], importlibs: Collection[str]
) -> str | None:
    """The module `importlib.import_module("a.b")` or `__import__("a.b")` loads, when its name
    is a literal; a computed name cannot be checked statically, and a relative one stays in its
    package. `functions`: the names bound to such a function here (`__import__`, an imported
    `import_module`); `importlibs`: the names bound to the importlib module."""
    func = node.func
    loads = (isinstance(func, ast.Name) and func.id in functions) or (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id in importlibs
    )
    name = node.args[0] if loads and node.args else None
    if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
        return None
    return name.value if name.value[:1] not in ("", ".") else None


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
