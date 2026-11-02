"""DOC-SAMPLE, for the docs check (scripts/check_docs.py): a code sample copied from a tested
file still matches that file, so a page never shows code that no longer runs (the design's 14).

A sample is a fenced code block that follows a link to a `.py` file, with no other fence
between them: the last such link before the block names its source. Its lines, indentation
aside and blank lines left out, must appear in that file in order and one after another, as
the file's own lines do with its blank lines left out. Nothing may be elided: a `...` line is
a line like any other. A block with no `.py` link before it is not a sample, and history
([docs] historical) is not read; a link that does not resolve is DOC-LINK's.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scripts._common import Violation
from scripts.doc_text import FENCE, extract_links, lines_of, living_docs
from scripts.harness_config import HarnessConfig


def check_samples(root: Path, config: HarnessConfig, markdown: Sequence[Path]) -> list[Violation]:
    violations = []
    for md, rel in living_docs(root, markdown, config.docs.historical):
        links = [link for link in extract_links(md, root) if link.target.suffix == ".py"]
        closed = 0  # the line the previous block's fence closed on
        for opened, sample, end in _blocks(md):
            source = next((k for k in reversed(links) if closed < k.line < opened), None)
            closed = end
            if source is None or not source.target.is_file() or not sample:
                continue
            if not source.target.is_relative_to(root):
                continue
            found = _found(sample, source.target)
            if found < len(sample):
                line, text = sample[found]
                shown = source.target.relative_to(root).as_posix()
                problem = f"the sample from {shown} no longer matches it, from its line `{text}` on"
                fix = (
                    f"Copy the block again from {shown} (its lines in order, indentation aside), "
                    "or link the file it now comes from; a block that is no sample needs no "
                    ".py link right before it."
                )
                violations.append(Violation(rel, line, "DOC-SAMPLE", problem, fix))
    return violations


def _blocks(md: Path) -> list[tuple[int, list[tuple[int, str]], int]]:
    """(the opening fence's line, the block's non-blank lines stripped and numbered, the
    closing fence's line) of each block; an unclosed one ends with the file."""
    found: list[tuple[int, list[tuple[int, str]], int]] = []
    inside: list[tuple[int, str]] | None = None
    opened = number = 0
    for number, line in lines_of(md):
        if FENCE.match(line) and inside is None:
            opened, inside = number, []
        elif FENCE.match(line) and inside is not None:
            found.append((opened, inside, number))
            inside = None
        elif inside is not None and line.strip():
            inside.append((number, line.strip()))
    if inside is not None:
        found.append((opened, inside, number))
    return found


def _found(sample: Sequence[tuple[int, str]], source: Path) -> int:
    """How many of the sample's first lines the source holds as consecutive lines."""
    wanted = [text for _, text in sample]
    lines = [s for line in source.read_text(encoding="utf-8").splitlines() if (s := line.strip())]
    best = 0
    for start in range(len(lines)):
        length = 0
        while length < len(wanted) and start + length < len(lines):
            if lines[start + length] != wanted[length]:
                break
            length += 1
        best = max(best, length)
    return best
