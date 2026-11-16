"""The recorder's out folder, checked with the library's checks before a run (`run_checkout`,
tested in the library's `test_run_checkout.py`): in the repository only under a git-ignored
`var/`, with the real git in a temporary repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from ole5_voice.evals import recorder_load
from ole5_voice.evals.recorder_state import RecorderError

from tests.t2_agentic_voice.testing.run_fakes import GIT, real_git_checkout


@pytest.fixture
def real_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return real_git_checkout(tmp_path, monkeypatch)


def test_the_recorder_run_from_a_linked_worktree_refuses_the_main_checkouts_tree(
    real_git: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`poe record --out` is refused in the repository outside its git-ignored var/: in the
    main checkout too when the recorder's code is a linked worktree's, so no take lands where
    git tracks it (plan 004, app8)."""
    main, linked = real_git, tmp_path / "linked"
    subprocess.run(
        [GIT, "worktree", "add", "-q", "--detach", str(linked)],
        cwd=main,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(recorder_load, "_REPO", linked)  # the recorder's code is the worktree's
    script = tmp_path / "script.toml"
    script.write_text(
        '[[lines]]\nid = "n01"\nkind = "request"\nlanguage = "english"\nsay = ["a b"]\n',
        encoding="utf-8",
    )
    for out in (main / "apps" / "takes", linked / "docs" / "takes"):
        with pytest.raises(RecorderError, match="outside its git-ignored var/"):
            recorder_load.load_recorder(out=out, script=script)
    for out in (main / "var" / "takes", linked / "var" / "takes", tmp_path / "takes"):
        assert recorder_load.load_recorder(out=out, script=script).out == out.resolve()


@pytest.mark.parametrize("runs_from", ["main", "a"])
def test_the_recorder_takes_a_folder_in_the_repository_only_under_its_own_or_the_mains_var(
    real_git: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs_from: str
) -> None:
    """With the worktrees nested in the main checkout, as `.claude/worktrees/<name>` are, an
    `--out` under another worktree's var/ is refused from the main checkout as before plan 004,
    and from a linked worktree too: a take there is lost when that worktree is removed."""
    main = real_git
    nested = {name: main / ".claude" / "worktrees" / name for name in ("a", "b")}
    for top in nested.values():
        subprocess.run(
            [GIT, "worktree", "add", "-q", "--detach", str(top)],
            cwd=main,
            check=True,
            capture_output=True,
        )
    own = main if runs_from == "main" else nested[runs_from]
    monkeypatch.setattr(recorder_load, "_REPO", own)
    script = tmp_path / "script.toml"
    script.write_text(
        '[[lines]]\nid = "n01"\nkind = "request"\nlanguage = "english"\nsay = ["a b"]\n',
        encoding="utf-8",
    )
    refused = [main / "apps" / "takes", own / "docs" / "takes", nested["b"] / "var" / "takes"]
    if own != main:
        refused.append(main / ".claude" / "takes")
    for out in refused:
        with pytest.raises(RecorderError, match="outside its git-ignored var/"):
            recorder_load.load_recorder(out=out, script=script)
    for out in (own / "var" / "takes", main / "var" / "takes", tmp_path / "takes"):
        assert recorder_load.load_recorder(out=out, script=script).out == out.resolve()
