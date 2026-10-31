"""DOC-MILESTONE and DOC-REF, for the docs check (scripts/check_docs.py): what docs and code
cite must exist.

- Milestone numbers change when the roadmap is re-planned, so references to them rot silently.
  Living docs cite only milestones in the roadmap's table (rows `| Mx | ...`); code never cites
  one. History ([docs] historical) keeps the numbers of its time.
- Every cited decision (D-NNN), tech-debt item (TD-NNN), golden principle (GP-NN), plan
  (plan NNN), and security invariant (invariant N) exists where harness.toml's [references]
  says it is recorded. History may cite retired debt, principles, and invariants, but never a
  missing decision or plan: those are superseded or completed, never removed.

The formats parsed here are a contract with the docs: a decision is a heading `## D-NNN ...`,
a debt item a table row `| TD-NNN | ...`, a principle a row `| GP-NN | ...`, a plan a file
`NNN-slug.md`, and an invariant a line `N. **Title.** ...` under `## Invariants`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.harness_config import DocsConfig, HarnessConfig

# A code with a decimal part (M2.5, a clothing size, a diagnosis code) is not a milestone.
_MILESTONE = re.compile(r"\bM(\d{1,2})\b(?!\.\d)")
_ROADMAP_ROW = re.compile(r"^\|\s*M(\d{1,2})\s*\|", re.MULTILINE)


def lines_of(path: Path) -> Iterator[tuple[int, str]]:
    yield from enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)


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
    for md in markdown:
        rel = md.relative_to(root).as_posix()
        if rel.startswith(config.docs.historical):
            continue
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


@dataclass(frozen=True)
class Registry:
    """A kind of reference that docs and code cite, and where its entries are recorded."""

    kind: str
    cited: re.Pattern[str]  # group 1 holds the cited number(s)
    homes: tuple[str, ...]  # where the entries are recorded; skipped when none exists
    entries: Callable[[Path], set[str]]  # the recorded numbers, given the repository root
    retired_in_history: bool  # entries can be removed, so history may cite retired ones


def _matches(home: str, pattern: str) -> Callable[[Path], set[str]]:
    regex = re.compile(pattern, re.MULTILINE)
    return lambda root: set(regex.findall((root / home).read_text(encoding="utf-8")))


def _invariants(home: str) -> Callable[[Path], set[str]]:
    def entries(root: Path) -> set[str]:
        text = (root / home).read_text(encoding="utf-8")
        section = text.split("\n## Invariants\n", 1)[-1].split("\n## ", 1)[0]
        return set(re.findall(r"^(\d+)\. \*\*", section, re.MULTILINE))

    return entries


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
                _matches(refs.decisions, r"^## D-(\d{3}) "),
                retired_in_history=False,  # decisions are superseded, never removed
            )
        )
    if refs.tech_debt:
        found.append(
            Registry(
                "tech-debt item",
                re.compile(r"\bTD-(\d{3})\b"),
                (refs.tech_debt,),
                _matches(refs.tech_debt, r"^\| TD-(\d{3}) \|"),
                retired_in_history=True,
            )
        )
    if refs.golden_principles:
        found.append(
            Registry(
                "golden principle",
                re.compile(r"\bGP-(\d{2})\b"),
                (refs.golden_principles,),
                _matches(refs.golden_principles, r"^\| GP-(\d{2}) \|"),
                retired_in_history=True,
            )
        )
    if refs.invariants:
        found.append(
            Registry(
                "invariant",
                re.compile(r"\b(?:[Ii]nvariants?|inv\.) (\d+(?:(?:, | and )\d+)*)"),
                (refs.invariants,),
                _invariants(refs.invariants),
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
