"""The checks before a run: a clean, linked worktree, never the main checkout.

Built by plan 002's Track E; until then a stub.
"""

from __future__ import annotations

from pathlib import Path

_STUB = "worktree.py is built by plan 002's Track E"


def run_commit(folder: Path) -> str:
    """The commit a run in `folder` measures; refuses the main checkout and a dirty tree."""
    raise NotImplementedError(_STUB)
