"""The docs as the docs check (scripts/check_docs.py, its rule modules) and `poe gc` read them:
which Markdown files there are, their lines, and their prose, the lines outside code fences.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

# A line that opens or closes a code fence.
FENCE = re.compile(r"^\s*(```|~~~)")


def markdown_files(root: Path) -> list[Path]:
    """The *.md files at the root and every one under docs/."""
    files = list(root.glob("*.md"))
    docs = root / "docs"
    if docs.is_dir():
        files.extend(docs.rglob("*.md"))
    return sorted(files)


def lines_of(path: Path) -> Iterator[tuple[int, str]]:
    """The file's lines, numbered from 1."""
    yield from enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)


def prose_lines(path: Path) -> Iterator[tuple[int, str]]:
    """The file's lines outside code fences, numbered from 1; the fence lines are left out."""
    fenced = False
    for number, line in lines_of(path):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            yield number, line
