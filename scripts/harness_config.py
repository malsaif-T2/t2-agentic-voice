"""The harness's settings: harness.toml at the repository root, read once into typed values.

Every check takes a HarnessConfig (their tests pass small ones of their own), so a project
changes its rules by editing harness.toml, never the checks. A mistake in the file, such as a
layer that imports an unknown layer or a cycle in the layer graph, is a HARNESS-CONFIG
violation with a FIX line, like any other. The architecture's tables are read by
scripts/harness_arch.py, the rest here.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._common import Violation, report
from scripts.harness_arch import ArchConfig, missing_facades, parse_arch
from scripts.harness_toml import CONFIG_FILE, FIX, RULE, Lines, Table

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
        return self.arch.package_dir

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
    if missing := missing_facades(root, config.arch, lines):
        raise HarnessConfigError(missing)
    return config


def parse_config(data: dict[str, Any], lines: Lines) -> HarnessConfig:
    problems: list[Violation] = []
    for name in sorted(set(data) - set(_TABLES)):
        problem = f"unknown table [{name}]"
        fix = "Remove it, or put another tool's settings under [tool.<name>]."
        problems.append(Violation(CONFIG_FILE, lines.of(name), RULE, problem, fix))
    arch = parse_arch(data, lines, problems)
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


Check = Callable[[Path, HarnessConfig], tuple[list[Violation], int]]


def load_or_report(name: str, root: Path) -> HarnessConfig | None:
    """The config, for a command's `main`; None once its violations are printed as every check
    prints them, so the command returns 1."""
    try:
        return load_config(root)
    except HarnessConfigError as error:
        report(name, error.violations, 1)
        return None


def run_check(name: str, root: Path, check: Check) -> int:
    """A check's `main`: load the config, run the check, print the outcome, return the code."""
    config = load_or_report(name, root)
    if config is None:
        return 1
    violations, checked = check(root, config)
    return report(name, violations, checked)
