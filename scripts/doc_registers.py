"""DOC-REGISTER, for the docs check (scripts/check_docs.py): the registers that docs and code
cite keep their shape, and never give one number to two entries.

Two sessions sharing a checkout can each take the next free number for a plan or a decision;
the second one then silently shadows the first, and every citation of the number becomes
ambiguous. So:
- no two plans (across the active and the completed folders) share a number;
- every decision heading is `## D-NNN · Title · YYYY-MM-DD · Status`, Status starting with
  Proposed, Accepted, Rejected, `Amended by D-NNN`, or `Superseded by D-NNN` (anything may
  follow it, as in `Accepted (a setting; not the default)`), and no two share a number;
- no two tech-debt rows, golden-principle rows, or security invariants share a number.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from scripts._common import Violation
from scripts.harness_config import HarnessConfig

_FENCE = re.compile(r"^\s*(```|~~~)")
DECISION_HEADING = re.compile(
    r"^## D-(\d{3}) · [^·]+ · \d{4}-\d{2}-\d{2} · "
    r"(?:Proposed|Accepted|Rejected|Amended by D-\d{3}|Superseded by D-\d{3})\b.*$"
)
_DECISION = re.compile(r"^## D-(\d+)")
_ROWS = {
    "tech-debt item": (re.compile(r"^\| TD-(\d{3}) \|"), "TD-"),
    "golden principle": (re.compile(r"^\| GP-(\d{2}) \|"), "GP-"),
}
_INVARIANT = re.compile(r"^(\d+)\. \*\*")
REUSED_FIX = (
    "Give the newer entry the next free number and fix its citations; check with the other "
    "sessions first (WORKING-RULES.md, 'Commits and parallel sessions'). Numbers are never "
    "reused, even after an entry is removed."
)


def check_registers(root: Path, config: HarnessConfig) -> list[Violation]:
    violations = _plans(root, config)
    refs = config.references
    if refs.decisions and (root / refs.decisions).is_file():
        violations += _decisions(refs.decisions, _lines(root / refs.decisions))
    for kind, home in (
        ("tech-debt item", refs.tech_debt),
        ("golden principle", refs.golden_principles),
    ):
        if home and (root / home).is_file():
            pattern, prefix = _ROWS[kind]
            numbered = _numbered(_lines(root / home), pattern)
            violations += _reused(home, kind, prefix, numbered)
    if refs.invariants and (root / refs.invariants).is_file():
        violations += _reused(refs.invariants, "invariant", "", _invariants(root / refs.invariants))
    return violations


def _lines(path: Path) -> list[tuple[int, str]]:
    """The file's lines outside code fences, numbered from 1."""
    found, fenced = [], False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            found.append((number, line))
    return found


def _numbered(
    lines: Iterable[tuple[int, str]], pattern: re.Pattern[str]
) -> Iterator[tuple[int, str]]:
    for number, line in lines:
        if found := pattern.match(line):
            yield number, found.group(1)


def _reused(
    home: str, kind: str, prefix: str, entries: Iterable[tuple[int, str]]
) -> list[Violation]:
    """A violation at each entry whose number an earlier entry already has."""
    first: dict[str, int] = {}
    violations = []
    for line, number in entries:
        if number in first:
            problem = f"{kind} {prefix}{number} is used twice (first on line {first[number]})"
            violations.append(Violation(home, line, "DOC-REGISTER", problem, REUSED_FIX))
        else:
            first[number] = line
    return violations


def _decisions(home: str, lines: list[tuple[int, str]]) -> list[Violation]:
    violations = []
    for line, text in lines:
        if _DECISION.match(text) and not DECISION_HEADING.match(text):
            violations.append(
                Violation(
                    home,
                    line,
                    "DOC-REGISTER",
                    "a decision heading is not in the shape the checks read",
                    "Write it as `## D-NNN · Title · YYYY-MM-DD · Status`, with a Status that "
                    "starts with Proposed, Accepted, Rejected, `Amended by D-NNN`, or "
                    f"`Superseded by D-NNN` ({home}, 'The format').",
                )
            )
    return violations + _reused(home, "decision", "D-", _numbered(lines, _DECISION))


def _invariants(path: Path) -> list[tuple[int, str]]:
    """The numbered invariants under `## Invariants`, with their lines."""
    found, inside = [], False
    for line, text in _lines(path):
        if text.startswith("## "):
            inside = text.rstrip() == "## Invariants"
        elif inside and (match := _INVARIANT.match(text)):
            found.append((line, match.group(1)))
    return found


def _plans(root: Path, config: HarnessConfig) -> list[Violation]:
    plans = config.plans
    files = [
        f"{folder}/{path.name}"
        for folder in (plans.active, plans.completed)
        for path in sorted((root / folder).glob("*.md"))
        if re.match(r"^\d{3}-", path.name)
    ]
    by_number: dict[str, list[str]] = {}
    for shown in files:
        by_number.setdefault(shown.rsplit("/", 1)[1][:3], []).append(shown)
    fix = (
        "The plan that had the number first (`git log --diff-filter=A -- <file>`) keeps it; give "
        "the other the next free number, rename its file, and fix its citations and links. "
        "Check with the other sessions first (WORKING-RULES.md, 'Commits and parallel sessions')."
    )
    return [
        Violation(shown, 1, "DOC-REGISTER", f"plan number {number} is also used by {other}", fix)
        for number, shared in by_number.items()
        if len(shared) > 1
        for shown in shared
        for other in [", ".join(s for s in shared if s != shown)]
    ]
