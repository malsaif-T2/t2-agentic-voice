"""DOC-PLAN, for the docs check (scripts/check_docs.py): execution plans are named, headed, and
placed as docs/plans/README.md says, since other checks and commands read them.

- A plan's file is `NNN-short-slug.md` (DOC-REF finds plans by their number, and `poe gc` finds
  garbage-collection rounds by their name).
- It holds the sections that harness.toml's [plans] sections names.
- Its Status line has the full shape for its folder, since `poe gc` reads the milestone and the
  Completed date from it:
  `Status: active · Milestone: Mx · Started: YYYY-MM-DD` in the active folder, and the same
  with `Status: completed` and ` · Completed: YYYY-MM-DD` at the end in the completed one. Work
  outside the milestones says `Milestone: none (maintenance)` (or another reason in brackets).
- Several plans can be active at once, so the roadmap links every active plan: from its
  milestone's row, or from its "Outside the milestones" line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scripts._common import Violation
from scripts.harness_config import PlansConfig

FILE_NAME = re.compile(r"^\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
# A garbage-collection round's file name (docs/harness/garbage-collection.md), as `poe gc` finds
# the last round.
ROUND = re.compile(r"^\d{3}-garbage-collection-\d+\.md$")
_STATUS = re.compile(r"^Status: (\w+)(.*)$", re.MULTILINE)
_MILESTONE = r"Milestone: (M\d+|none \([^)\n]+\))"
_DATE = r"(\d{4}-\d{2}-\d{2})"
SHAPES = {
    "active": re.compile(rf"^ · {_MILESTONE} · Started: {_DATE}$"),
    "completed": re.compile(rf"^ · {_MILESTONE} · Started: {_DATE} · Completed: {_DATE}$"),
}
SHOWN_SHAPES = {
    "active": "Status: active · Milestone: Mx · Started: YYYY-MM-DD",
    "completed": "Status: completed · Milestone: Mx · Started: YYYY-MM-DD · Completed: YYYY-MM-DD",
}
# The plan template, which holds every section; tests/harness/test_check_docs.py checks it does.
TEMPLATE = "docs/plans/TEMPLATE.md"


@dataclass(frozen=True)
class PlanStatus:
    """A plan's Status line, read: the one parser of the shape, for DOC-PLAN and `poe gc`."""

    status: str  # "active" or "completed"
    milestone: str  # "Mx", or "none (maintenance)"
    started: str
    completed: str | None  # None for an active plan


def plan_status(text: str) -> PlanStatus | None:
    """The plan's first Status line, when it has the full shape of the status it names."""
    stated = _STATUS.search(text)
    if stated is None or stated.group(1) not in SHAPES:
        return None
    found = SHAPES[stated.group(1)].match(stated.group(2).rstrip())
    if found is None:
        return None
    milestone, started, *completed = found.groups()
    return PlanStatus(stated.group(1), milestone, started, completed[0] if completed else None)


def check_plans(root: Path, plans: PlansConfig, roadmap_links: set[Path] | None) -> list[Violation]:
    """`roadmap_links`: where the roadmap's links point (normalized), or None without one."""
    violations: list[Violation] = []
    for plan_dir, status in ((plans.active, "active"), (plans.completed, "completed")):
        for plan in sorted((root / plan_dir).glob("*.md")):
            linked = roadmap_links is None or plan in roadmap_links
            found = _check_plan(plan, status, plans, linked=linked)
            shown = f"{plan_dir}/{plan.name}"
            violations += [Violation(shown, 1, "DOC-PLAN", problem, fix) for problem, fix in found]
    return violations


def _check_plan(
    plan: Path, status: str, plans: PlansConfig, *, linked: bool
) -> list[tuple[str, str]]:
    """(problem, fix) for each way the plan breaks the format."""
    found: list[tuple[str, str]] = []
    if not FILE_NAME.match(plan.name):
        found.append(
            (
                "a plan's file name is not NNN-short-slug.md",
                "Rename it: the next free three-digit number, a hyphen, and a lowercase slug "
                "(docs/plans/README.md), and fix the links to it.",
            )
        )
    text = plan.read_text(encoding="utf-8")
    missing = [
        heading
        for heading in plans.sections
        if not re.search(rf"^{re.escape(heading)}\s*$", text, flags=re.MULTILINE)
    ]
    if missing:
        found.append(
            (
                f"plan is missing section(s): {', '.join(missing)}",
                "Add the missing headings, each on its own line, as the plan template "
                f"({TEMPLATE}) spells them.",
            )
        )
    stated, parsed = _STATUS.search(text), plan_status(text)
    milestone = None
    if stated is None or stated.group(1) != status:
        found.append(
            (
                f"a plan in the {status} folder must say 'Status: {status}' on its own line",
                "Fix the Status line, or move the plan to the folder its status names "
                "(docs/plans/README.md).",
            )
        )
    elif parsed is None:
        found.append(
            (
                "the Status line is not in the shape the checks read",
                f"Write it as `{SHOWN_SHAPES[status]}`, with `Milestone: none (maintenance)` "
                "for work outside the milestones (docs/plans/README.md); `poe gc` reads it.",
            )
        )
    else:
        milestone = parsed.milestone
    if status == "active" and not linked:
        where = (
            f"{milestone}'s row"
            if milestone is not None and milestone.startswith("M")
            else "the 'Outside the milestones' line (a plan outside the milestones)"
        )
        found.append(
            (
                "an active plan is not linked from the roadmap",
                f"Link it from {where} in {plans.roadmap}.",
            )
        )
    return found
