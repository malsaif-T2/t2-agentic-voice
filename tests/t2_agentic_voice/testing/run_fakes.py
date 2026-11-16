"""What the tests of a measurement run's shared parts use, the library's and every app's: a fake
`git` for the checks before a run (`run_checkout.py`), a real one in a temporary repository with
no user's or system's configuration, and a clock that moves only when the run pauses."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from t2_agentic_voice.evals import GitResult

COMMIT = "ab" * 20
GIT = shutil.which("git") or "git"


@dataclass
class FakeGit:
    """A `Git` that answers the commands `run_checkout.py` asks, for a run worktree `top` linked
    to the checkout `main` (or the main checkout itself, when `top` is `main`)."""

    top: Path
    main: Path
    dirty: bool = False
    ignored: tuple[Path, ...] = ()  # folders whose paths git ignores, in the main checkout
    commit: str = COMMIT
    failing: tuple[str, ...] = ()  # commands that fail, by their first word after options
    calls: list[tuple[tuple[str, ...], Path]] = field(default_factory=list)

    def __call__(self, args: Sequence[str], cwd: Path) -> GitResult:
        command = tuple(args)
        self.calls.append((command, cwd))
        verb = next(word for word in command if not word.startswith("-"))
        if verb in self.failing:
            return GitResult(128, "")
        if command[:2] == ("rev-parse", "--path-format=absolute"):
            return GitResult(0, f"{self.top.as_posix()}\n")
        if command[:2] == ("worktree", "list"):
            trees = [self.main] + ([self.top] if self.top != self.main else [])
            return GitResult(
                0, "".join(f"worktree {t.as_posix()}\0HEAD {COMMIT}\0\0" for t in trees)
            )
        if command[:2] == ("rev-parse", "--verify"):
            return GitResult(0, f"{self.commit}\n")
        if verb == "status":
            return GitResult(0, " M apps/x.py\0" if self.dirty else "")
        if verb == "check-ignore":
            path = Path(command[-1])
            inside = any(path.is_relative_to(i.resolve()) for i in self.ignored)
            return GitResult(0 if inside else 1, "")
        raise AssertionError(f"git {command} is not faked")


class FakeClock:
    """Seconds that pass only when the run pauses, each pause recorded."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.pauses: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.now += seconds


def real_git_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A main checkout with one commit and a `.gitignore` of `var/`, read by the real git with
    no user's or system's configuration; skips the test when git is not installed."""
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
