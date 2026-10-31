"""Whether a garbage-collection round is due: the opening section of `uv run poe gc`.

The last round is the highest-numbered completed `NNN-garbage-collection-K.md` plan, and the
commit that moved it to the completed plans' folder; before the first round, the count starts
at the repository's first commit. A round is due when, since then:
- a milestone completed (a completed plan names it in its Status line:
  `Status: completed · Milestone: Mx · ...`);
- [gc] due_after_commits or more commits landed (harness.toml);
- a layer grades below what [quality] doc (docs/harness/quality.md) records. Grades are
  compared only when coverage is measured alike (both with it, or both without), since a score
  without coverage is out of the other signals.

It informs and blocks nothing: the owner asks for a round when they see fit
(docs/harness/garbage-collection.md).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.harness_config import HarnessConfig, HarnessConfigError, load_config
from scripts.quality import Grade, grades, measured_coverage, read_sources

ROOT = Path(__file__).resolve().parents[1]
_ROUND = re.compile(r"^\d{3}-garbage-collection-\d+\.md$")
_MILESTONE = re.compile(r"^Status: completed · Milestone: (M\d+)\b", re.MULTILINE)
_COMPLETED_ON = re.compile(r"Completed: (\d{4}-\d{2}-\d{2})")
# A row of quality.md's grades: layer, letter, score, coverage.
_RECORDED = re.compile(r"^\| (\w+) \| \*\*([A-D])\*\* \| \d+ \| ([^|]+) \|", re.MULTILINE)


@dataclass(frozen=True)
class Round:
    plan: str  # its file name in the completed plans' folder
    completed: str  # its Completed date
    commit: str | None  # the commit that completed it: None before it is committed, or no git


@dataclass(frozen=True)
class Since:
    milestones: list[str]  # "Mx (plan NNN)"
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
    rounds = sorted(p.name for p in (root / completed).glob("*.md") if _ROUND.match(p.name))
    if not rounds:
        return None
    plan = rounds[-1]
    found = _COMPLETED_ON.search((root / completed / plan).read_text(encoding="utf-8"))
    # The commit that added it to completed/, not the one that wrote it in active/: a user's
    # `log.follow` would follow the move back there.
    path = f"{completed}/{plan}"
    added = git(root, "-c", "log.follow=false", "log", "--diff-filter=A", "--format=%H", "--", path)
    return Round(plan, found.group(1) if found else "?", added.split()[-1] if added else None)


def milestones_since(root: Path, completed: str, commit: str | None) -> list[str]:
    """Milestone plans in completed/ now (committed or not) that were not there at `commit`
    (all of them when `commit` is None: no round yet)."""
    listed = git(root, "ls-tree", "--name-only", f"{commit}:{completed}") if commit else None
    before = set((listed or "").split())
    found = []
    for path in sorted((root / completed).glob("*.md")):
        milestone = _MILESTONE.search(path.read_text(encoding="utf-8"))
        if path.name not in before and milestone:
            found.append(f"{milestone.group(1)} (plan {path.name[:3]})")
    return found


def recorded_grades(text: str) -> dict[str, tuple[str, bool]]:
    """Each layer's letter in quality.md, and whether its coverage was measured."""
    return {
        layer: (letter, coverage.strip() != "not measured")
        for layer, letter, coverage in _RECORDED.findall(text)
    }


def compare(
    recorded: dict[str, tuple[str, bool]], now: Sequence[Grade]
) -> tuple[list[str], list[str]]:
    """(layers graded lower now, layers not compared because coverage is measured differently)."""
    drops, not_compared = [], []
    for g in now:
        if g.layer not in recorded:
            continue
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
        now = grades(read_sources(root), measured_coverage(root), config)
    drops, not_compared = compare(recorded, now)
    start = last.commit if last is not None else None
    commits = git(root, "rev-list", "--count", f"{start}..HEAD" if start else "HEAD") or "0"
    since = Since(milestones_since(root, completed, start), int(commits), drops, not_compared)
    return render(last, since, config)


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Say whether a garbage-collection round is due."
    ).parse_args(argv)
    try:
        config = load_config(ROOT)
    except HarnessConfigError as error:
        print(error)
        return 1
    print(section(ROOT, config), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
