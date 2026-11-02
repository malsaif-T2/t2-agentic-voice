"""The checks before a run, through `git`: the run's checkout is a clean linked worktree, never
the main checkout (evaluation.md, "Running"), and its `--out` is a new folder outside every
worktree that may be removed, which git never tracks.

Every question goes to `git`, through a `Git` function the tests replace with a fake; nothing
here reads a file of the repository. A refusal is an `InvalidRequestError` whose message says
what to do (a FIX line).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from t2_agentic_voice import InvalidRequestError

_COMMIT = re.compile(r"[0-9a-f]{40}")


class GitResult(NamedTuple):
    """What one `git` command gave: its exit code and its standard output."""

    returncode: int
    stdout: str


# `git <args>` in a folder.
Git = Callable[[Sequence[str], Path], GitResult]


def run_git(args: Sequence[str], cwd: Path) -> GitResult:
    """`git <args>` run in `cwd`, its standard output read as UTF-8, never a prompt."""
    executable = shutil.which("git")
    if executable is None:
        raise refused("git is not on PATH", "install git, or run from a shell where it is")
    done = subprocess.run(  # noqa: S603 - git, with arguments built here
        [executable, *args], cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL, check=False
    )
    return GitResult(done.returncode, done.stdout.decode("utf-8", errors="replace"))


def refused(reason: str, fix: str) -> InvalidRequestError:
    """A run refused before anything is sent, for `reason`, with what to do."""
    return InvalidRequestError(f"The run is refused: {reason}. FIX: {fix}.")


@dataclass(frozen=True)
class Checkout:
    """The worktree a run's code and data come from, as git describes it."""

    top: Path  # this worktree's top folder
    main: Path  # the main checkout's top folder
    worktrees: tuple[Path, ...]  # every worktree's top folder, the main checkout's first
    commit: str  # HEAD, in full
    clean: bool  # nothing changed, staged or untracked (ignored files aside)

    @property
    def linked(self) -> bool:
        return not _same(self.top, self.main)

    def refusal(self) -> InvalidRequestError | None:
        """Why a run may not start here, or None when it may."""
        if not self.linked:
            return refused(
                "this is the main checkout",
                "run from a linked worktree at the measurement commit (`git worktree add`)",
            )
        if not self.clean:
            return refused(
                "the worktree has changes (`git status` is not empty)",
                "commit or remove them, so the run measures one commit",
            )
        return None


def inspect(folder: Path, git: Git = run_git) -> Checkout:
    """The checkout `folder` is in; refused when it is in none, or has no commit."""
    found = git(["rev-parse", "--path-format=absolute", "--show-toplevel"], folder)
    if found.returncode != 0 or not found.stdout.strip():
        raise refused(f"{folder} is not inside a git checkout", "run from the run's worktree")
    top = Path(found.stdout.strip())
    trees = worktree_tops(top, git)
    head = git(["rev-parse", "--verify", "HEAD"], top)
    commit = head.stdout.strip()
    if head.returncode != 0 or not _COMMIT.fullmatch(commit):
        raise refused("the checkout has no commit git names in 40 hex digits", "commit first")
    status = git(["--no-optional-locks", "status", "--porcelain", "-z"], top)
    if status.returncode != 0:
        raise refused("`git status` failed in the checkout", "run `git status` there and fix it")
    return Checkout(
        top=top,
        main=trees[0] if trees else top,
        worktrees=trees or (top,),
        commit=commit,
        clean=not status.stdout,
    )


def worktree_tops(folder: Path, git: Git = run_git) -> tuple[Path, ...]:
    """The top folder of every worktree of the repository `folder` is in, the main checkout's
    first, as `git worktree list` gives them; none when git names no checkout there, or is not
    on PATH."""
    try:
        listed = git(["worktree", "list", "--porcelain", "-z"], folder)
    except (InvalidRequestError, OSError):  # no git on PATH, or no such folder
        return ()
    if listed.returncode != 0:
        return ()
    return tuple(
        Path(field.removeprefix("worktree "))
        for field in listed.stdout.split("\0")
        if field.startswith("worktree ")
    )


def run_commit(folder: Path, git: Git = run_git) -> str:
    """The commit a run in `folder` measures; refuses the main checkout and a dirty tree."""
    checkout = inspect(folder, git)
    if (problem := checkout.refusal()) is not None:
        raise problem
    return checkout.commit


def check_out(out: Path, checkout: Checkout, git: Git = run_git) -> Path:
    """`out` as an absolute path, when a run may write there: a folder that does not exist yet,
    outside the run's own worktree (removed once the runs are done) and every other linked
    worktree, and, inside the main checkout, only where git ignores it (its `var/`), so a
    scorecard is never committed. Refused otherwise, before anything is sent."""
    target = out.expanduser().resolve()
    if target.exists():
        raise refused(
            f"--out {target} exists", "give a new folder; a run never writes into an old one"
        )
    holders = [tree for tree in (checkout.top, *checkout.worktrees) if _inside(target, tree)]
    if not holders:
        return target
    holder = max(holders, key=lambda tree: len(tree.resolve().parts))  # the innermost
    if _same(holder, checkout.top):
        raise refused(
            "--out is inside the run's worktree, which is removed after the runs",
            "give a folder under the main checkout's var/, or outside the repository",
        )
    if not _same(holder, checkout.main):
        raise refused("--out is inside another linked worktree", "give a folder of this run's own")
    ignored = git(["check-ignore", "-q", "--", str(target)], checkout.main)
    if ignored.returncode != 0:
        raise refused(
            "--out is inside the repository where git would track it",
            "give a folder under the main checkout's var/, which git ignores, or outside it",
        )
    return target


def _same(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def _inside(target: Path, tree: Path) -> bool:
    return target.is_relative_to(tree.resolve())
