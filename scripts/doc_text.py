"""The docs as the docs check (scripts/check_docs.py, its rule modules) and `poe gc` read them:
which Markdown files there are, their lines, their code blocks, their prose (the lines outside
those blocks), and the local links in their prose.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

# A line that opens or closes a code fence.
_FENCE = re.compile(r"^\s*(```|~~~)")
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


def living_docs(
    root: Path, markdown: Sequence[Path], historical: tuple[str, ...]
) -> Iterator[tuple[Path, str]]:
    """(doc, its path from the root) for each doc that is not history ([docs] historical)."""
    for md in markdown:
        rel = md.relative_to(root).as_posix()
        if not rel.startswith(historical):
            yield md, rel


def lines_of(path: Path) -> Iterator[tuple[int, str]]:
    """The file's lines, numbered from 1."""
    yield from enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)


@dataclass(frozen=True)
class Block:
    """A fenced code block: the fence lines' numbers and the numbered lines between them."""

    opened: int
    lines: tuple[tuple[int, str], ...]
    closed: int  # an unclosed block ends with the file


def code_blocks(path: Path) -> list[Block]:
    """The file's code blocks, in order: a fence line opens one, and the next fence line closes
    it, whatever its marker."""
    blocks: list[Block] = []
    inside: list[tuple[int, str]] | None = None
    opened = number = 0
    for number, line in lines_of(path):
        if _FENCE.match(line) and inside is None:
            opened, inside = number, []
        elif _FENCE.match(line) and inside is not None:
            blocks.append(Block(opened, tuple(inside), number))
            inside = None
        elif inside is not None:
            inside.append((number, line))
    if inside is not None:
        blocks.append(Block(opened, tuple(inside), number))
    return blocks


def prose_lines(path: Path) -> Iterator[tuple[int, str]]:
    """The file's lines outside code blocks, numbered from 1; the fence lines are left out."""
    fenced = {n for block in code_blocks(path) for n in range(block.opened, block.closed + 1)}
    yield from ((number, line) for number, line in lines_of(path) if number not in fenced)


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
