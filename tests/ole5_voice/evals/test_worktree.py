"""The checks before a run (evaluation.md, "Running"): a clean linked worktree, never the main
checkout, and an `--out` that is new, outside every worktree that may be removed, and ignored by
git. With a fake `git`, and once with the real one in a temporary repository."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from ole5_voice.evals.worktree import Checkout, GitResult, check_out, inspect, run_commit, run_git
from t2_agentic_voice import InvalidRequestError

from tests.ole5_voice.evals.run_support import COMMIT, FakeGit

GIT = shutil.which("git") or "git"


def _trees(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    top = main / ".claude" / "worktrees" / "run"
    top.mkdir(parents=True)
    return main, top


def test_a_clean_linked_worktree_runs_at_its_commit(tmp_path: Path) -> None:
    main, top = _trees(tmp_path)
    git = FakeGit(top, main)
    assert run_commit(top / "apps", git) == COMMIT
    assert [cwd for _, cwd in git.calls] == [top / "apps"] + [top] * 3  # then at the top
    checkout = inspect(top, git)
    assert (checkout.linked, checkout.clean, checkout.refusal()) == (True, True, None)
    assert checkout.worktrees == (main, top)


def test_the_main_checkout_is_refused(tmp_path: Path) -> None:
    main, _ = _trees(tmp_path)
    with pytest.raises(InvalidRequestError, match=r"the main checkout\. FIX: run from a linked"):
        run_commit(main, FakeGit(main, main))


def test_a_dirty_tree_is_refused(tmp_path: Path) -> None:
    main, top = _trees(tmp_path)
    with pytest.raises(InvalidRequestError, match="has changes"):
        run_commit(top, FakeGit(top, main, dirty=True))


@pytest.mark.parametrize(
    ("failing", "commit", "message"),
    [
        ("rev-parse", COMMIT, "not inside a git checkout"),
        ("", "abc", "no commit"),  # git names a commit in 40 hex digits; a 64-digit one is refused
        ("status", COMMIT, "`git status` failed"),
    ],
)
def test_a_folder_git_cannot_describe_is_refused(
    tmp_path: Path, failing: str, commit: str, message: str
) -> None:
    main, top = _trees(tmp_path)
    with pytest.raises(InvalidRequestError, match=message):
        inspect(top, FakeGit(top, main, commit=commit, failing=(failing,)))


def test_a_checkout_git_lists_no_worktree_of_is_its_own_main(tmp_path: Path) -> None:
    def git(args: Sequence[str], cwd: Path) -> GitResult:
        return FakeGit(tmp_path, tmp_path)(args, cwd) if args[0] != "worktree" else GitResult(0, "")

    checkout = inspect(tmp_path, git)
    assert (checkout.main, checkout.worktrees, checkout.linked) == (tmp_path, (tmp_path,), False)


def _checkout(tmp_path: Path) -> tuple[Checkout, FakeGit]:
    main, top = _trees(tmp_path)
    other = main / ".claude" / "worktrees" / "other"
    other.mkdir()
    git = FakeGit(top, main, ignored=(main / "var", main / ".claude"))
    checkout = inspect(top, git)
    return Checkout(checkout.top, checkout.main, (*checkout.worktrees, other), COMMIT, True), git


def test_an_out_under_the_main_checkouts_ignored_var_or_outside_is_taken(tmp_path: Path) -> None:
    checkout, git = _checkout(tmp_path)
    assert check_out(checkout.main / "var" / "runs" / "r1", checkout, git).name == "r1"
    assert check_out(tmp_path / "elsewhere" / "r1", checkout, git) == tmp_path / "elsewhere" / "r1"
    asked = [args for args, _ in git.calls if args[0] == "check-ignore"]
    assert asked == [("check-ignore", "-q", "--", str((checkout.main / "var/runs/r1").resolve()))]


@pytest.mark.parametrize(
    ("where", "message"),
    [
        ("main/var", "exists"),
        ("main/.claude/worktrees/run/var/r1", "inside the run's worktree"),
        ("main/.claude/worktrees/other/r1", "inside another linked worktree"),
        ("main/apps/r1", "where git would track it"),
    ],
)
def test_an_out_that_exists_or_may_be_lost_or_tracked_is_refused(
    tmp_path: Path, where: str, message: str
) -> None:
    checkout, git = _checkout(tmp_path)
    (tmp_path / "main" / "var").mkdir()
    with pytest.raises(InvalidRequestError, match=message):
        check_out(tmp_path / where, checkout, git)


def test_an_out_named_relatively_resolves_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, git = _checkout(tmp_path)
    monkeypatch.chdir(checkout.top)  # a run's own folder: `var/r1` would be lost with it
    with pytest.raises(InvalidRequestError, match="inside the run's worktree"):
        check_out(Path("var/r1"), checkout, git)


def test_without_git_on_path_a_run_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(InvalidRequestError, match="git is not on PATH"):
        run_git(["status"], tmp_path)


@pytest.fixture
def real_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A main checkout with one commit and a `.gitignore` of `var/`, read by the real git with
    no user's or system's configuration."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # no repository above it
    main = tmp_path / "main"
    main.mkdir()
    (main / ".gitignore").write_text("var/\n", encoding="utf-8", newline="\n")
    who = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
    for args in (["init", "-q", "-b", "main"], ["add", ".gitignore"], [*who, "commit", "-qm", "x"]):
        subprocess.run([GIT, *args], cwd=main, check=True, capture_output=True)
    return main


def test_the_real_git_answers_as_the_checks_expect(real_git: Path, tmp_path: Path) -> None:
    main = real_git
    with pytest.raises(InvalidRequestError, match="the main checkout"):
        run_commit(main)
    top = tmp_path / "run"
    subprocess.run(
        [GIT, "worktree", "add", "-q", "--detach", str(top)],
        cwd=main,
        check=True,
        capture_output=True,
    )
    commit = run_commit(top / ".")
    assert len(commit) == 40
    checkout = inspect(top)
    assert check_out(main / "var" / "r1", checkout).name == "r1"
    with pytest.raises(InvalidRequestError, match="git would track it"):
        check_out(main / "apps" / "r1", checkout)
    (top / "new.txt").write_text("x", encoding="utf-8")  # untracked counts as a change
    with pytest.raises(InvalidRequestError, match="has changes"):
        run_commit(top)
    loose = tmp_path / "loose"
    loose.mkdir()
    with pytest.raises(InvalidRequestError, match="not inside a git checkout"):
        inspect(loose)
