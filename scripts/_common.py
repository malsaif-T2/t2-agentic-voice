"""Shared violation type and reporting for harness checks.

Every check prints violations as

    path:line: [RULE-ID] what is wrong
        FIX: how to fix it

so an agent can remediate from the message alone, without asking a human.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    problem: str
    fix: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.problem}\n    FIX: {self.fix}"


def report(check_name: str, violations: Sequence[Violation], checked: int) -> int:
    """Print the outcome and return a process exit code."""
    if not violations:
        print(f"{check_name}: OK ({checked} files checked)")
        return 0
    for violation in sorted(violations):
        print(violation)
    print(f"{check_name}: {len(violations)} violation(s). Fix every item above, then re-run.")
    return 1
