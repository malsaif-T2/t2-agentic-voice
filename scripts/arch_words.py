"""ARCH-WORDS, for the architecture check (scripts/check_architecture.py): the library's src/
never names an app built on it.

Each word of [package] banned_words (an app's name, its ticket system, its own hosts) is looked
for in any case, inside words too (`ole5_voice` holds `ole5`), in every source and text file
under [package] root, and in each such file's path below that folder. Two things are skipped on
purpose:
- `__pycache__/`: a bytecode file holds its module's absolute path, and a checkout may sit in a
  folder whose name holds a banned word;
- the folders above [package] root, for the same reason: only the path below it is read.
So the library stays usable by every team, with nothing shaped by one app underneath (D-020).
"""

from __future__ import annotations

from pathlib import Path

from scripts._common import Violation
from scripts.harness_config import ArchConfig

# The files read: Python, and the text a package ships (docs, data, web assets).
SUFFIXES = frozenset({".py", ".md", ".toml", ".json", ".txt", ".js", ".html", ".css"})
SKIPPED = "__pycache__"
FIX = (
    "The library serves every team, so it never names an app: move this into the app, or make "
    "it a setting or an argument the app passes in. If the word is not an app's name, change "
    "[package] banned_words in harness.toml and record why in docs/design/decisions.md."
)


def check_words(root: Path, arch: ArchConfig) -> tuple[list[Violation], int]:
    """(each banned word found, with its line; the number of files read)."""
    src = root / arch.package_root
    words = sorted({w.casefold() for w in arch.banned_words})
    if not words or not src.is_dir():
        return [], 0
    violations: list[Violation] = []
    files = [p for p in sorted(src.rglob("*")) if _is_read(p, src)]
    for path in files:
        display = path.relative_to(root).as_posix()
        below = path.relative_to(src).as_posix().casefold()
        for word in (w for w in words if w in below):
            problem = f"the path names '{word}', a banned word ([package] banned_words)"
            violations.append(Violation(display, 1, "ARCH-WORDS", problem, FIX))
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            folded = line.casefold()
            for word in (w for w in words if w in folded):
                problem = f"'{word}' is a banned word in the library ([package] banned_words)"
                violations.append(Violation(display, lineno, "ARCH-WORDS", problem, FIX))
    return violations, len(files)


def _is_read(path: Path, src: Path) -> bool:
    return (
        path.suffix.lower() in SUFFIXES
        and SKIPPED not in path.relative_to(src).parts
        and path.is_file()
    )
