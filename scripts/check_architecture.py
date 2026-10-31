"""Mechanically enforce the architecture that ARCHITECTURE.md describes: `uv run poe arch`.

The rules' settings live in harness.toml ([package], [layers], [[owners]], [[restricted]],
[[subpackages]], [[apps]], [rules], [modules]); this module only applies them.

Rules
  ARCH-LAYER      internal imports follow the layer graph (an `importlib.import_module` or
                  `__import__` of a literal name counts as an import); code lives inside a
                  layer; a subpackage's narrower rules hold; a layer never imports from the
                  package root, which only re-exports the public API
  ARCH-PUBLIC     an app in [[apps]] imports the library only through [package] public, and no
                  other app (its import statements); the library never imports an app
  ARCH-OWNER      a library in [[owners]] is imported only by its layers
  ARCH-PRINT      no print() and no sys.stdout/sys.stderr writes, outside [rules]
                  output_allowed_files; use the structured logger
  ARCH-ENV        the environment (os.environ, os.getenv, ...) is read only in [rules]
                  env_allowed_files, however `os` is imported
  ARCH-CONSTRUCT  a class in [[restricted]] is constructed (or validated into being) only by
                  its layers
  ARCH-DOC        the architecture doc's layer table matches [layers] and [[owners]], row by
                  row (scripts/arch_doc.py)
  ARCH-SIZE, ARCH-FMT, ARCH-PARSE   every module, in src/ and the support folders
                  (scripts/module_rules.py)
  HARNESS-CONFIG  harness.toml itself is valid (scripts/harness_config.py)
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Collection, Sequence
from pathlib import Path

from scripts._common import Violation
from scripts.arch_doc import check_layer_doc
from scripts.harness_config import AppRule, ArchConfig, HarnessConfig, run_check
from scripts.module_rules import check_support, parse_module

ROOT = Path(__file__).resolve().parents[1]
ROOT_LAYER = "<package root>"
CHANGE_RULE_FIX = (
    "If the rule itself is wrong, change it in harness.toml and ARCHITECTURE.md together, and "
    "record why in docs/design/decisions.md."
)
ENV_ATTRS = frozenset({"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"})
_STREAMS = frozenset({"stdout", "stderr"})


class _ModuleChecker(ast.NodeVisitor):
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
            self._add(
                line,
                "ARCH-LAYER",
                f"layer '{self.layer}' imports '{'.'.join(parts)}' from the package root",
                "Import it from the layer that defines it; the package root only re-exports the "
                "public API for apps.",
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
                "Use the structured logger: `log = get_logger(__name__)`; "
                "`log.info('event_name', key=value)`.",
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
        """The module `importlib.import_module("a.b")` or `__import__("a.b")` loads, split on
        dots, when its name is a literal; a computed name cannot be checked statically."""
        func = node.func
        loads = (isinstance(func, ast.Name) and func.id in self.import_functions) or (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id in self.importlib_names
        )
        name = node.args[0] if loads and node.args else None
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            return None
        return name.value.split(".") if name.value[:1] not in ("", ".") else None

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
        self._add(
            line,
            "ARCH-ENV",
            f"{what} used outside {allowed}",
            "Add a field to Settings in core/config.py (and .env.example), then read it via "
            "`get_settings()` or an injected Settings instance.",
        )


class _AppChecker(ast.NodeVisitor):
    """An app's import statements (ARCH-PUBLIC): the library only through its public modules,
    and no other app."""

    def __init__(self, arch: ArchConfig, *, app: str, display: str) -> None:
        self.arch = arch
        self.app = app
        self.display = display
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check(alias.name.split("."), node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module:
            base = node.module.split(".")
            # `from <library> import core`: the name may be a layer, so check the module too.
            if base == [self.arch.package]:
                for alias in node.names:
                    if alias.name in self.arch.layers:
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
                "...`). If apps need it, export it from the package root, or add the module to "
                "[package] public in harness.toml, and record why in docs/design/decisions.md."
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
        return [Violation("harness.toml", 1, "HARNESS-CONFIG", f"{init} does not exist", fix)], 0
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


def check_file(
    path: Path, package_dir: Path, display_root: Path, arch: ArchConfig
) -> list[Violation]:
    rel_parts = path.relative_to(package_dir).parts
    rel = "/".join(rel_parts)
    display = path.relative_to(display_root).as_posix()
    source = path.read_text(encoding="utf-8")
    tree, violations = parse_module(display, source, arch.max_module_lines)
    if tree is None:
        return violations
    layers = ", ".join(arch.layers)
    if len(rel_parts) == 1:
        layer = ROOT_LAYER
        if rel != "__init__.py":
            problem = f"module '{rel}' sits outside every layer"
            fix = f"Move it into one of: {layers}. {CHANGE_RULE_FIX}"
            violations.append(Violation(display, 1, "ARCH-LAYER", problem, fix))
    else:
        layer = rel_parts[0]
        if layer not in arch.layers:
            violations.append(
                Violation(
                    display,
                    1,
                    "ARCH-LAYER",
                    f"unknown layer '{layer}'",
                    f"Place the code in one of: {layers}. To add a layer, add it to [layers] "
                    "in harness.toml and to ARCHITECTURE.md together, and record why in "
                    "docs/design/decisions.md.",
                )
            )
    checker = _ModuleChecker(arch, layer=layer, rel=rel, display=display)
    checker.visit(tree)
    return violations + checker.violations


def check_tree(
    package_dir: Path, display_root: Path, arch: ArchConfig
) -> tuple[list[Violation], int]:
    files = sorted(package_dir.rglob("*.py"))
    violations: list[Violation] = []
    for path in files:
        violations.extend(check_file(path, package_dir, display_root, arch))
    return violations, len(files)


def check_repo(root: Path, config: HarnessConfig) -> tuple[list[Violation], int]:
    arch = config.arch
    package_dir = root / config.package_dir
    if not (package_dir / "__init__.py").is_file():
        missing = Violation(
            "harness.toml",
            1,
            "HARNESS-CONFIG",
            f"{config.package_dir}/__init__.py does not exist",
            "Set [package] name and root in harness.toml to the library's package, or create "
            f"{config.package_dir}/__init__.py.",
        )
        return [missing], 0
    violations, checked = check_tree(package_dir, root, arch)
    for app in arch.apps:
        found, count = check_app(root, app, arch)
        violations, checked = violations + found, checked + count
    support, support_count = check_support(root, arch.support_dirs, arch.max_module_lines)
    return violations + support + check_layer_doc(root, arch), checked + support_count


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="Check the layer and module rules.").parse_args(argv)
    return run_check("check_architecture", ROOT, check_repo)


if __name__ == "__main__":
    sys.exit(main())
