"""Whether a garbage-collection round is due (scripts/gc_due.py): measured from the last round's
commit, on a repository built here, and on this one.

This file is in harness.toml's [docs] code_exempt: its made-up plans are cited by number.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.gc_due import (
    ROOT,
    Round,
    Since,
    compare,
    git,
    reasons,
    recorded_grades,
    render,
    section,
)
from scripts.harness_config import HarnessConfig, load_config
from scripts.quality import Grade
from tests.harness.support import config, write

QUALITY = """\
| Layer | Grade | Score | Coverage | Modules within 300 lines |
| --- | --- | --- | --- | --- |
| core | **A** | 100 | 99% | 100% |
| api | **B** | 85 | 90% | 100% |
| scripts | **D** | 68 | not measured | 81% |
"""
DUE_AFTER = 5  # the synthetic config's [gc] due_after_commits


def milestone(number: int) -> str:
    """A milestone of the made-up plans here, built so the line does not cite one."""
    return f"M{number}"


def _grade(layer: str, coverage: float | None, letter: str = "A") -> Grade:
    return Grade(layer, 4, 1000, coverage, 1.0, (200, "a.py"), 0.0, 0, 1.0, 95.0, letter)


def test_grades_are_compared_only_when_coverage_is_measured_alike() -> None:
    recorded = recorded_grades(QUALITY)
    assert recorded == {"core": ("A", True), "api": ("B", True), "scripts": ("D", False)}
    now = [
        _grade("core", 0.5, "B"),  # below its A
        _grade("api", 1.0, "A"),  # better than recorded: not a drop
        _grade("scripts", 0.9, "C"),  # measured now, but not when recorded
        _grade("domain", 1.0),  # not recorded
    ]
    assert compare(recorded, now) == (["core: A in quality.md, B now"], ["scripts"])


def test_each_trigger_makes_a_round_due() -> None:
    quiet = Since(milestones=[], commits=DUE_AFTER - 1, drops=[], not_compared=[])
    assert reasons(quiet, DUE_AFTER) == []
    done = f"{milestone(4)} (plan 006)"
    assert reasons(Since([done], 0, [], []), DUE_AFTER) == [f"{done} completed"]
    assert reasons(Since([], DUE_AFTER, [], []), DUE_AFTER) == [f"{DUE_AFTER} commits"]
    drop = Since([], 0, ["api: A in quality.md, B now"], [])
    assert reasons(drop, DUE_AFTER) == ["api graded lower"]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, HarnessConfig]:
    """A git repository with no user or system configuration (no signing, no hooks)."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    for name, value in {
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(name, value)
    root = tmp_path / "repo"
    loaded = config(root)
    write(root, {"docs/harness/quality.md": QUALITY, "docs/plans/completed/.keep": ""})
    assert git(root, "init", "-q") is not None
    git(root, "config", "log.follow", "true")  # a user's setting that must not mislead it
    return root, loaded


def _plan(root: Path, name: str, milestone: str, folder: str = "completed") -> None:
    header = (
        f"Status: completed · Milestone: {milestone} · Started: 2026-01-12 · Completed: 2026-01-15"
    )
    write(root, {f"docs/plans/{folder}/{name}": f"# {name}\n\n{header}\n"})


def _commit(root: Path) -> None:
    git(root, "add", "-A")
    assert git(root, "commit", "-q", "--allow-empty", "-m", "change") is not None


def test_before_the_first_round_the_count_starts_at_the_first_commit(
    repo: tuple[Path, HarnessConfig],
) -> None:
    root, loaded = repo
    empty = section(root, loaded, now=[])  # no commit yet
    assert "Since the first commit (no round has completed yet):" in empty
    assert "- commits: 0 " in empty
    assert "Due: no." in empty
    _plan(root, "001-scaffold.md", milestone(1))
    _commit(root)
    done = f"{milestone(1)} (plan 001)"
    found = section(root, loaded, now=[])
    assert f"- milestones completed: {done}\n- commits: 1 " in found
    assert f"Due: yes ({done} completed)." in found


def test_a_round_counts_from_the_commit_that_completed_it(repo: tuple[Path, HarnessConfig]) -> None:
    root, loaded = repo
    _plan(root, "003-api-surface.md", milestone(2))
    _plan(root, "004-garbage-collection-1.md", "none (maintenance)", folder="active")
    _commit(root)  # the round is written, and still active
    _commit(root)
    round_plan = "docs/plans/{}/004-garbage-collection-1.md"
    git(root, "mv", round_plan.format("active"), round_plan.format("completed"))
    assert "not committed yet" in section(root, loaded, now=[])

    _commit(root)  # the round completes: the count starts here, not where it was written
    after_round = section(root, loaded, now=[_grade("core", 1.0)])
    assert "Since the last round (plan 004, completed 2026-01-15)" in after_round
    assert "- milestones completed: none\n- commits: 0 " in after_round  # 003 came before it
    assert "Due: no." in after_round

    _commit(root)
    _commit(root)
    _plan(root, "005-reports.md", milestone(3))  # completed, not yet committed
    later = section(root, loaded, now=[_grade("core", 0.5, "B")])
    done = f"{milestone(3)} (plan 005)"
    assert f"- milestones completed: {done}\n- commits: 2 " in later
    assert "core: A in quality.md, B now" in later
    assert f"Due: yes ({done} completed; core graded lower)." in later


def test_this_repository_says_whether_a_round_is_due() -> None:
    found = section(ROOT, load_config(ROOT), now=[])
    assert found.startswith("# Is a garbage-collection round due?")


def test_render_says_which_layers_were_not_compared(tmp_path: Path) -> None:
    since = Since([], 3, [], ["core", "domain"])
    text = render(
        Round("007-garbage-collection-2.md", "2026-02-02", "abc"), since, config(tmp_path)
    )
    assert "(not compared: core, domain;" in text
    assert text.endswith(
        "Due: no.\nA round runs when the owner asks (docs/harness/garbage-collection.md).\n"
    )
