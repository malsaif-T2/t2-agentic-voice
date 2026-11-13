"""DOC-MILESTONE, DOC-PLANWORDS and DOC-REF, for the docs check (scripts/check_docs.py): what
docs and code cite must exist, and code names nothing that a completed plan leaves meaningless.

- Milestone numbers change when the roadmap is re-planned, so references to them rot silently.
  Living docs cite only milestones in the roadmap's table (rows `| Mx | ...`); code never cites
  one. History ([docs] historical) keeps the numbers of its time.
- A plan's tracks and blocks (the word and a letter or a number after it) mean nothing once the
  plan is completed, so code never names one (DOC-PLANWORDS): it names the capability, the
  decision or the plan. Read in the code and in the root's TOML files, whose comments are read
  as the code's.
- Every cited decision (D-NNN), tech-debt item (TD-NNN), golden principle (GP-NN), plan
  (plan NNN), and security invariant (invariant N) exists where harness.toml's [references]
  says it is recorded. History may cite retired debt, principles, and invariants, but never a
  missing decision or plan: those are superseded or completed, never removed.

The entries are read by scripts/doc_registers.py, which DOC-REGISTER uses too: a decision is a
heading `## D-NNN ...`, a debt item a table row `| TD-NNN | ...`, a principle a row
`| GP-NN | ...`, and an invariant a line `N. **Title.** ...` under `## Invariants`, each outside
code fences; a plan is a file `NNN-slug.md`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.doc_registers import entries as recorded_entries
from scripts.doc_text import lines_of, living_docs
from scripts.harness_config import DocsConfig, HarnessConfig

# A code with a decimal part (M2.5, a clothing size, a diagnosis code) is not a milestone.
_MILESTONE = re.compile(r"\bM(\d{1,2})\b(?!\.\d)")
_ROADMAP_ROW = re.compile(r"^\|\s*M(\d{1,2})\s*\|", re.MULTILINE)
# A plan's work unit: one of its tracks or blocks, named by a capital letter or a number.
_PLAN_UNIT = re.compile(r"\b(?:Tracks?|Blocks?)\s+(?:[A-Z]|\d+)\b")
_PLAN_UNIT_FIX = (
    "A plan's tracks and blocks mean nothing once it is completed: name the capability, or "
    "cite the decision (D-NNN) or the plan (plan NNN) instead."
)


def code_files(root: Path, docs: DocsConfig) -> list[Path]:
    """Python files that may cite docs; the docs check's own tests need fake citations."""
    return [
        path
        for directory in docs.code_dirs
        for path in sorted((root / directory).rglob("*.py"))
        if path.relative_to(root).as_posix() not in docs.code_exempt
    ]


def check_milestones(
    root: Path, config: HarnessConfig, markdown: Sequence[Path]
) -> list[Violation]:
    roadmap = root / config.plans.roadmap
    text = roadmap.read_text(encoding="utf-8") if roadmap.is_file() else ""
    known = set(_ROADMAP_ROW.findall(text))
    violations: list[Violation] = []
    for md, rel in living_docs(root, markdown, config.docs.historical):
        for lineno, line in lines_of(md):
            for match in _MILESTONE.finditer(line):
                if match.group(1) not in known:
                    violations.append(
                        Violation(
                            rel,
                            lineno,
                            "DOC-MILESTONE",
                            f"M{match.group(1)} is not a milestone in {config.plans.roadmap}",
                            "Cite a milestone listed in the roadmap table, or better, the decision "
                            "(D-NNN) or capability you mean.",
                        )
                    )
    for path in code_files(root, config.docs):
        for lineno, line in lines_of(path):
            found = _MILESTONE.search(line)
            if found:
                violations.append(
                    Violation(
                        path.relative_to(root).as_posix(),
                        lineno,
                        "DOC-MILESTONE",
                        f"code cites milestone M{found.group(1)}",
                        "Milestone numbers change when the roadmap is re-planned; cite the "
                        "decision (D-NNN) or name the capability instead.",
                    )
                )
    return violations


def check_plan_words(root: Path, config: HarnessConfig) -> list[Violation]:
    """DOC-PLANWORDS: no code file, nor a TOML file at the root, names a plan's track or block."""
    files = [*code_files(root, config.docs), *sorted(root.glob("*.toml"))]
    violations: list[Violation] = []
    for path in files:
        for lineno, line in lines_of(path):
            found = _PLAN_UNIT.search(line)
            if found:
                problem = f"code names a plan's work unit, '{found.group(0)}'"
                rel = path.relative_to(root).as_posix()
                violations.append(Violation(rel, lineno, "DOC-PLANWORDS", problem, _PLAN_UNIT_FIX))
    return violations


@dataclass(frozen=True)
class Registry:
    """A kind of reference that docs and code cite, and where its entries are recorded."""

    kind: str
    cited: re.Pattern[str]  # group 1 holds the cited number(s)
    homes: tuple[str, ...]  # where the entries are recorded; skipped when none exists
    entries: Callable[[Path], set[str]]  # the recorded numbers, given the repository root
    retired_in_history: bool  # entries can be removed, so history may cite retired ones


def _recorded(home: str, kind: str) -> Callable[[Path], set[str]]:
    return lambda root: {number for _, number in recorded_entries(root / home, kind)}


def registries(config: HarnessConfig) -> list[Registry]:
    refs, plans = config.references, config.plans
    found = [
        Registry(
            "plan",
            re.compile(r"\b[Pp]lans? (\d{3})\b"),
            (plans.active, plans.completed),
            lambda root: {
                p.name[:3] for d in (plans.active, plans.completed) for p in (root / d).glob("*.md")
            },
            retired_in_history=False,
        )
    ]
    if refs.decisions:
        found.append(
            Registry(
                "decision",
                re.compile(r"\bD-(\d{3})\b"),
                (refs.decisions,),
                _recorded(refs.decisions, "decision"),
                retired_in_history=False,  # decisions are superseded, never removed
            )
        )
    if refs.tech_debt:
        found.append(
            Registry(
                "tech-debt item",
                re.compile(r"\bTD-(\d{3})\b"),
                (refs.tech_debt,),
                _recorded(refs.tech_debt, "tech-debt item"),
                retired_in_history=True,
            )
        )
    if refs.golden_principles:
        found.append(
            Registry(
                "golden principle",
                re.compile(r"\bGP-(\d{2})\b"),
                (refs.golden_principles,),
                _recorded(refs.golden_principles, "golden principle"),
                retired_in_history=True,
            )
        )
    if refs.invariants:
        found.append(
            Registry(
                "invariant",
                re.compile(r"\b(?:[Ii]nvariants?|inv\.) (\d+(?:(?:, | and )\d+)*)"),
                (refs.invariants,),
                _recorded(refs.invariants, "invariant"),
                retired_in_history=True,
            )
        )
    return found


def check_references(
    root: Path, config: HarnessConfig, markdown: Sequence[Path]
) -> list[Violation]:
    """Every cited reference exists, so a reader who follows one finds what it points to."""
    active = [
        (registry, registry.entries(root))
        for registry in registries(config)
        if any((root / home).exists() for home in registry.homes)
    ]
    violations: list[Violation] = []
    for path in [*markdown, *code_files(root, config.docs)]:
        rel = path.relative_to(root).as_posix()
        historical = rel.startswith(config.docs.historical)
        for lineno, line in lines_of(path):
            for registry, known in active:
                if historical and registry.retired_in_history:
                    continue
                for match in registry.cited.finditer(line):
                    for number in re.findall(r"\d+", match.group(1)):
                        if number not in known:
                            violations.append(
                                Violation(
                                    rel,
                                    lineno,
                                    "DOC-REF",
                                    f"{registry.kind} {number} is not in "
                                    f"{' or '.join(registry.homes)}",
                                    "Record it there (or restore it), or cite the entry you mean.",
                                )
                            )
    return violations
