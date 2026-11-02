"""The docs as the docs check (scripts/check_docs.py, its rule modules) and `poe gc` read them:
which Markdown files there are, their lines, their prose (the lines outside code fences), and
the local links in their prose.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

# A line that opens or closes a code fence.
FENCE = re.compile(r"^\s*(```|~~~)")
_LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_EXTERNAL = ("http://", "https://", "mailto:")


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


@dataclass(frozen=True)
class Link:
    line: int
    raw: str
    target: Path


def extract_links(md: Path, root: Path) -> list[Link]:
    """Local links in `md`, ignoring code blocks, inline code, external URLs and anchors."""
    links: list[Link] = []
    for lineno, line in prose_lines(md):
        for match in _LINK.finditer(_INLINE_CODE.sub("", line)):
            raw = match.group(1).removeprefix("<").removesuffix(">")
            if raw.startswith(_EXTERNAL) or raw.startswith("#"):
                continue
            path_part = unquote(raw.split("#", 1)[0])
            base = root if path_part.startswith("/") else md.parent
            # normpath, not resolve(): resolve() adopts the on-disk case on Windows, which
            # would hide exactly the case mismatches that break links on Linux CI.
            target = Path(os.path.normpath(base / path_part.lstrip("/")))
            links.append(Link(lineno, raw, target))
    return links
