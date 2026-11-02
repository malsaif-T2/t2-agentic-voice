"""Whether a garbage-collection round is due: the opening section of `uv run poe gc`.

The last round is the highest-numbered completed `NNN-garbage-collection-K.md` plan, and the
commit that moved it to the completed plans' folder; before the first round, the repository's
first commit. The count starts after that commit. A round is due when, since then:
- a milestone completed: a plan whose Status line names it completed
  (`Status: completed · Milestone: Mx · ...`, read by scripts/doc_plans.py), and no active plan
  names it;
- [gc] due_after_commits or more commits landed (harness.toml), merges left out: a merge
  repeats the commits of its branch;
- a layer grades below what [quality] doc (docs/harness/quality.md) records. Grades are
  compared only when coverage is measured alike (both with it, or both without), since a score
  without coverage is out of the other signals.

It informs and blocks nothing: the owner asks for a round when they see fit
(docs/harness/garbage-collection.md).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.doc_plans import ROUND, plan_status
from scripts.harness_config import HarnessConfig, PlansConfig, load_or_report
from scripts.quality import (
    EMPTY,
    Grade,
    grades,
    measured_coverage,
    read_sources,
    recorded_grades,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Round:
    plan: str  # its file name in the completed plans' folder
    completed: str  # its Completed date
    commit: str | None  # the commit that completed it: None before it is committed, or no git


@dataclass(frozen=True)
class Since:
    milestones: list[str]  # "Mx (plan NNN)", or "Mx (plans NNN, NNN)"
    commits: int
    drops: list[str]  # "api: A in quality.md, B now"
    not_compared: list[str]  # layers whose coverage is measured differently now


def git(root: Path, *args: str) -> str | None:
    """git's output in `root`, or None without git or when the command fails."""
    executable = shutil.which("git")
    if executable is None:
        return None
    done = subprocess.run(  # noqa: S603 - git, with arguments built here
        [executable, *args], cwd=root, capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else None


def last_round(root: Path, completed: str) -> Round | None:
    rounds = sorted(p.name for p in (root / completed).glob("*.md") if ROUND.match(p.name))
    if not rounds:
        return None
    plan = rounds[-1]
    status = plan_status((root / completed / plan).read_text(encoding="utf-8"))
    # The commit that added it to completed/, not the one that wrote it in active/: a user's
    # `log.follow` would follow the move back there.
    path = f"{completed}/{plan}"
    added = git(root, "-c", "log.follow=false", "log", "--diff-filter=A", "--format=%H", "--", path)
    done = status.completed if status is not None and status.completed else "?"
    return Round(plan, done, added.split()[-1] if added else None)


def milestones_since(root: Path, plans: PlansConfig, commit: str | None) -> list[str]:
    """Each milestone a plan completed since `commit` (every completed plan counts when it is
    None: no round yet), committed or not, unless an active plan still names it: "Mx (plan
    NNN)", with every such plan."""
    listed = git(root, "ls-tree", "--name-only", f"{commit}:{plans.completed}") if commit else None
    before = set((listed or "").split())
    still_open = {milestone for _, milestone in _milestones(root, plans.active, "active")}
    done: dict[str, list[str]] = {}
    for name, milestone in _milestones(root, plans.completed, "completed"):
        if name not in before and milestone not in still_open:
            done.setdefault(milestone, []).append(name[:3])
    return [
        f"{milestone} (plan{'s' if len(numbers) > 1 else ''} {', '.join(numbers)})"
        for milestone, numbers in done.items()
    ]


def _milestones(root: Path, folder: str, status: str) -> list[tuple[str, str]]:
    """(file name, milestone) for each plan in `folder` whose Status line says `status` and
    names a milestone, in the shape DOC-PLAN enforces."""
    found = []
    for path in sorted((root / folder).glob("*.md")):
        stated = plan_status(path.read_text(encoding="utf-8"))
        if stated is not None and stated.status == status and stated.milestone.startswith("M"):
            found.append((path.name, stated.milestone))
    return found


def commits_since(root: Path, start: str | None) -> int:
    """The commits after `start` (after the first commit when it is None), merges left out."""
    first = git(root, "rev-list", "--max-parents=0", "HEAD") if start is None else start
    if not first:
        return 0  # no commit yet, or no git
    excluded = [f"^{commit}" for commit in first.split()]
    return int(git(root, "rev-list", "--count", "--no-merges", "HEAD", *excluded) or 0)


def compare(
    recorded: dict[str, tuple[str, bool]], now: Sequence[Grade]
) -> tuple[list[str], list[str]]:
    """(layers graded lower now, layers not compared because coverage is measured differently)."""
    drops, not_compared = [], []
    for g in now:
        if g.layer not in recorded or g.letter == EMPTY:
            continue  # not graded before, or no code left to grade
        letter, measured = recorded[g.layer]
        if measured != (g.coverage is not None):
            not_compared.append(g.layer)
        elif g.letter > letter:  # letters run from A, the best
            drops.append(f"{g.layer}: {letter} in quality.md, {g.letter} now")
    return drops, not_compared


def reasons(since: Since, due_after_commits: int) -> list[str]:
    """Why a round is due; empty when it is not."""
    found = [f"{m} completed" for m in since.milestones]
    if since.commits >= due_after_commits:
        found.append(f"{since.commits} commits")
    return found + [f"{d.split(':')[0]} graded lower" for d in since.drops]


def render(last: Round | None, since: Since, config: HarnessConfig) -> str:
    """The section; `last` is None before the first round."""
    compared = "none" if not since.drops else "; ".join(since.drops)
    due_after = config.gc.due_after_commits
    start = (
        f"Since the last round (plan {last.plan[:3]}, completed {last.completed}):"
        if last is not None
        else "Since the first commit (no round has completed yet):"
    )
    lines = [
        "# Is a garbage-collection round due?",
        "",
        start,
        f"- milestones completed: {', '.join(since.milestones) or 'none'}",
        f"- commits: {since.commits} ({due_after} make a round due)",
        f"- layers graded below {config.quality.doc}: {compared}",
    ]
    if since.not_compared:
        lines.append(
            f"  (not compared: {', '.join(since.not_compared)}; their coverage is measured "
            "after `uv run poe test`)"
        )
    why = reasons(since, due_after)
    lines += ["", f"Due: yes ({'; '.join(why)})." if why else "Due: no."]
    lines.append("A round runs when the owner asks (docs/harness/garbage-collection.md).")
    return "\n".join(lines) + "\n"


def section(root: Path, config: HarnessConfig, now: Sequence[Grade] | None = None) -> str:
    """The section in Markdown. `now`: the layers' grades, measured here when not given."""
    completed = config.plans.completed
    last = last_round(root, completed)
    if last is not None and last.commit is None:
        return (
            "# Is a garbage-collection round due?\n\n"
            f"Not known: plan {last.plan[:3]}, the last round, is not committed yet "
            "(or git is unavailable).\n"
        )
    doc = root / config.quality.doc
    recorded = recorded_grades(doc.read_text(encoding="utf-8")) if doc.is_file() else {}
    if now is None:
        now = grades(read_sources(root, config), measured_coverage(root), config)
    drops, not_compared = compare(recorded, now)
    start = last.commit if last is not None else None
    milestones = milestones_since(root, config.plans, start)
    since = Since(milestones, commits_since(root, start), drops, not_compared)
    return render(last, since, config)


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Say whether a garbage-collection round is due."
    ).parse_args(argv)
    config = load_or_report("gc_due", ROOT)
    if config is None:
        return 1
    print(section(ROOT, config), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
