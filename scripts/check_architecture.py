"""Mechanically enforce the architecture that ARCHITECTURE.md describes: `uv run poe arch`.

The rules' settings live in harness.toml ([package], [layers], [[owners]], [[restricted]],
[[bans]], [[subpackages]], [[apps]], [rules], [modules]); this module only applies them. The
rules read inside one module of the library (ARCH-LAYER's imports, ARCH-OWNER, ARCH-PRINT,
ARCH-ENV, ARCH-CONSTRUCT) are scripts/arch_module.py's; the others name their helper below.

Rules
  ARCH-LAYER      internal imports follow the layer graph (an `importlib.import_module` or
                  `__import__` of a literal name counts as an import); code lives inside a
                  layer; a subpackage's narrower rules hold; a layer never imports from the
                  package root or a facade, which only re-export the public API
  ARCH-PUBLIC     an app in [[apps]] imports the library only through [package] public, and no
                  other app (its import statements, scripts/arch_public.py); the library never
                  imports an app
  ARCH-FACADE     a facade ([package] facades) holds only a docstring, imports and `__all__`
                  (scripts/arch_facade.py)
  ARCH-WORDS      the library's src/ holds no word of [package] banned_words, in any case
                  (scripts/arch_words.py)
  ARCH-OWNER      a library in [[owners]] is imported only by its layers
  ARCH-BAN        a module a [[bans]] table names is never imported by the code it covers (a
                  part of the library or an app), its `allowed` modules aside
                  (scripts/arch_ban.py)
  ARCH-PRINT      no print() and no sys.stdout/sys.stderr writes, outside [rules]
                  output_allowed_files; use the structured logger
  ARCH-ENV        the environment (os.environ, os.getenv, ...) is read only in [rules]
                  env_allowed_files, however `os` is imported
  ARCH-CONSTRUCT  a class in [[restricted]] is constructed (or validated into being) only by
                  its layers, and a name in [[restricted]] is referred to only there
  ARCH-DOC        the architecture doc's layer table matches [layers] and [[owners]], row by
                  row (scripts/arch_doc.py)
  ARCH-DEPS       every outside module is declared by the project of the code that imports
                  it: a member's pyproject.toml, or the root's (scripts/arch_deps.py)
  ARCH-SIZE, ARCH-FMT, ARCH-PARSE   every module, in src/ and the support folders
                  (scripts/module_rules.py)
  HARNESS-CONFIG  harness.toml itself is valid (scripts/harness_config.py, harness_arch.py)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts._common import Violation
from scripts.arch_ban import check_bans
from scripts.arch_deps import check_deps
from scripts.arch_doc import check_layer_doc
from scripts.arch_facade import check_facade
from scripts.arch_module import CHANGE_RULE_FIX, ROOT_LAYER, ModuleChecker
from scripts.arch_public import check_app
from scripts.arch_words import check_words
from scripts.harness_arch import ArchConfig
from scripts.harness_config import HarnessConfig, run_check
from scripts.harness_toml import CONFIG_FILE, RULE
from scripts.module_rules import check_support, parse_module

ROOT = Path(__file__).resolve().parents[1]


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
        layer = ROOT_LAYER  # the package root's __init__.py, or a facade beside it
        if Path(rel).stem in arch.facade_names:
            violations += check_facade(display, tree)
        elif rel != "__init__.py":
            problem = f"module '{rel}' sits outside every layer"
            fix = (
                f"Move it into one of: {layers}. A public facade is listed in [package] "
                f"facades. {CHANGE_RULE_FIX}"
            )
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
    checker = ModuleChecker(arch, layer=layer, rel=rel, display=display)
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
            CONFIG_FILE,
            1,
            RULE,
            f"{config.package_dir}/__init__.py does not exist",
            "Set [package] name and root in harness.toml to the library's package, or create "
            f"{config.package_dir}/__init__.py.",
        )
        return [missing], 0
    violations, checked = check_tree(package_dir, root, arch)
    violations += check_words(root, arch)[0]  # its Python files are counted above already
    for app in arch.apps:
        found, count = check_app(root, app, arch)
        violations, checked = violations + found, checked + count
    support, support_count = check_support(root, arch.support_dirs, arch.max_module_lines)
    violations += check_bans(root, arch) + check_deps(root, arch)
    return violations + support + check_layer_doc(root, arch), checked + support_count


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="Check the layer and module rules.").parse_args(argv)
    return run_check("check_architecture", ROOT, check_repo)


if __name__ == "__main__":
    sys.exit(main())
