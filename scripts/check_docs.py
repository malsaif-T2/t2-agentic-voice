"""Mechanically verify the repository knowledge base (docs are the system of record):
`uv run poe docs`. Its settings are harness.toml's [docs], [plans], and [references].

Rules
  DOC-REQUIRED     the docs in [docs] required exist
  DOC-LINK         relative markdown links resolve, with exact filename case (Linux CI is
                   case-sensitive even when Windows and macOS are not)
  DOC-ORPHAN       every doc under docs/ is reachable from the entry doc by following links
                   (linking a folder makes the .md files directly inside it reachable)
  DOC-ENTRY        the entry doc stays a short map (at most [docs] max_entry_lines lines)
  DOC-PLACEHOLDER  no install placeholder (an uppercase name between double braces) is left
                   in any file of the repository, or in a file or folder name (hidden folders
                   other than .github/, and runtime output, are skipped)
  DOC-EOL          the docs, the code, and the root config files have LF line endings
  DOC-CONTROL      no doc holds a control character other than a tab and the line ends
  DOC-PLAN         plans are named NNN-slug.md, hold the [plans] sections, and have a full
                   Status line that matches their folder; the roadmap links every active plan
                   (scripts/doc_plans.py)
  DOC-REGISTER     no two plans, decisions, debt rows, principles, or invariants share a
                   number, and decision headings keep their shape (scripts/doc_registers.py)
  DOC-MILESTONE    living docs cite only roadmap milestones; code never cites milestones
  DOC-REF          every cited D-NNN, TD-NNN, GP-NN, plan NNN, and invariant N exists
                   (scripts/doc_refs.py, both)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from scripts._common import Violation
from scripts.doc_plans import check_plans
from scripts.doc_refs import check_milestones, check_references, lines_of
from scripts.doc_registers import check_registers
from scripts.harness_config import HarnessConfig, run_check

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
# Root files that the line-ending rule reads besides the docs and the code.
ROOT_CONFIG = ("*.toml", ".env.example")
# Folders the placeholder rule never enters (hidden ones are skipped too, except .github):
# runtime output and installed or built files, which are not ours to fill.
NOT_OURS = frozenset({"var", "node_modules", "build", "dist", "htmlcov", "__pycache__"})
_LARGEST = 1_000_000  # bytes: a larger file is data, not a file the kit wrote
# The C0 control characters and DEL, but the tab and the line ends: what a script makes of a
# Windows path's backslashes when it reads them as escapes (\v, \a), which no editor shows.
# A carriage return counts: `\r` in a path read as an escape leaves a lone one (CRLF is DOC-EOL's).
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f]")

_LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_EXTERNAL = ("http://", "https://", "mailto:")


@dataclass(frozen=True)
class Link:
    line: int
    raw: str
    target: Path


def markdown_files(root: Path) -> list[Path]:
    files = list(root.glob("*.md"))
    docs = root / "docs"
    if docs.is_dir():
        files.extend(docs.rglob("*.md"))
    return sorted(files)


def extract_links(md: Path, root: Path) -> list[Link]:
    """Local links in `md`, ignoring code blocks, inline code, external URLs and anchors."""
    links: list[Link] = []
    in_fence = False
    for lineno, line in lines_of(md):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
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


def exists_exact_case(path: Path, root: Path) -> bool:
    """`path.exists()`, but also require exact filename case for components inside `root`."""
    if not path.exists():
        return False
    root = root.resolve()
    current = path
    while current != root and root in current.parents:
        if current.name not in {child.name for child in current.parent.iterdir()}:
            return False
        current = current.parent
    return True


def reachable_docs(root: Path, entry: Path) -> set[Path]:
    seen: set[Path] = set()
    queue = [entry.resolve()]
    while queue:
        md = queue.pop().resolve()
        if md in seen or not md.is_file():
            continue
        seen.add(md)
        for link in extract_links(md, root):
            if link.target.is_dir():
                queue.extend(sorted(link.target.glob("*.md")))
            elif link.target.suffix == ".md":
                queue.append(link.target)
    return seen


def check_repo(root: Path, config: HarnessConfig) -> tuple[list[Violation], int]:
    root = root.resolve()
    docs = config.docs
    violations: list[Violation] = []
    for rel in docs.required:
        if not (root / rel).is_file():
            violations.append(
                Violation(
                    rel,
                    1,
                    "DOC-REQUIRED",
                    f"required document '{rel}' is missing",
                    "Restore it (see git history). If it was removed on purpose, take it out of "
                    "[docs] required in harness.toml and remove every link to it.",
                )
            )
    entry = root / docs.entry
    if entry.is_file():
        line_count = len(entry.read_text(encoding="utf-8").splitlines())
        if line_count > docs.max_entry_lines:
            violations.append(
                Violation(
                    docs.entry,
                    docs.max_entry_lines + 1,
                    "DOC-ENTRY",
                    f"{docs.entry} has {line_count} lines (max {docs.max_entry_lines})",
                    f"Keep {docs.entry} a map: move detail into a doc under docs/ and link to it.",
                )
            )
    files = markdown_files(root)
    violations += check_links(root, files)
    if entry.is_file():
        violations += check_orphans(root, entry, files, docs.entry)
    roadmap = root / config.plans.roadmap
    linked = {link.target for link in extract_links(roadmap, root)} if roadmap.is_file() else None
    violations += check_plans(root, config.plans, linked)
    violations += check_registers(root, config)
    violations += check_placeholders(root, config)
    violations += check_line_endings(root, config, files)
    violations += check_control_characters(root, files)
    violations += check_milestones(root, config, files)
    violations += check_references(root, config, files)
    return violations, len(files)


def check_links(root: Path, files: Sequence[Path]) -> list[Violation]:
    return [
        Violation(
            md.relative_to(root).as_posix(),
            link.line,
            "DOC-LINK",
            f"broken link '{link.raw}'",
            "Fix the path (relative to the linking file, exact filename case; wrap paths "
            "containing spaces in <...>) or remove the link.",
        )
        for md in files
        for link in extract_links(md, root)
        if not exists_exact_case(link.target, root)
    ]


def check_orphans(root: Path, entry: Path, files: Sequence[Path], shown: str) -> list[Violation]:
    reached = reachable_docs(root, entry)
    docs_dir = root / "docs"
    return [
        Violation(
            md.relative_to(root).as_posix(),
            1,
            "DOC-ORPHAN",
            f"not reachable from {shown} by following links",
            f"Link it from the most relevant index ({shown}, ARCHITECTURE.md, "
            "docs/plans/README.md, ...) or delete it if obsolete.",
        )
        for md in files
        if docs_dir in md.parents and md.resolve() not in reached
    ]


def repository_files(root: Path) -> Iterator[tuple[Path, bool]]:
    """(path, is_folder) for every file and folder the placeholder rule reads: everything but
    hidden folders (.git, .venv, .claude, ...; .github is read), NOT_OURS, and `.env` files
    other than `.env.example` (never read: they hold the developer's secrets)."""
    for folder, folders, names in root.walk():
        folders[:] = sorted(
            name
            for name in folders
            if name not in NOT_OURS and (not name.startswith(".") or name == ".github")
        )
        yield from ((folder / name, True) for name in folders)
        for name in sorted(names):
            if name.startswith(".env") and name != ".env.example":
                continue
            yield folder / name, False


def check_placeholders(root: Path, config: HarnessConfig) -> list[Violation]:
    """Install placeholders left unfilled: each is a value the owner has not given yet."""
    fix = (
        "Replace it with this project's value, from the owner's description (ask the owner when "
        "it is not there). A file that is a template on purpose goes in [docs] "
        "placeholders_allowed_in in harness.toml."
    )
    violations: list[Violation] = []
    for path, is_folder in repository_files(root):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(config.docs.placeholders_allowed_in):
            continue
        if found := PLACEHOLDER.search(path.name):
            what = "folder" if is_folder else "file"
            problem = f"the {what} name holds placeholder {found.group(0)}"
            violations.append(Violation(rel, 1, "DOC-PLACEHOLDER", problem, f"Rename it. {fix}"))
        if is_folder:
            continue
        try:
            if path.stat().st_size > _LARGEST:
                continue
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # not text, a broken link, or held open by another process
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in PLACEHOLDER.finditer(line):
                problem = f"placeholder {match.group(0)} is not filled in"
                violations.append(Violation(rel, lineno, "DOC-PLACEHOLDER", problem, fix))
    return violations


def check_line_endings(
    root: Path, config: HarnessConfig, markdown: Sequence[Path]
) -> list[Violation]:
    """CRLF in a file the repository stores as LF (.gitattributes): a Windows editor or a
    script's write_text, which rewrites every line in the diff."""
    others = [p for pattern in ROOT_CONFIG for p in sorted(root.glob(pattern))]
    code = [p for d in config.docs.code_dirs for p in sorted((root / d).rglob("*.py"))]
    violations: list[Violation] = []
    for path in [*markdown, *code, *others]:
        data = path.read_bytes()
        if b"\r\n" in data:
            line = data[: data.index(b"\r\n")].count(b"\n") + 1
            violations.append(
                Violation(
                    path.relative_to(root).as_posix(),
                    line,
                    "DOC-EOL",
                    "the file has CRLF line endings",
                    "Write it with LF endings: `uv run poe fmt` fixes Python files; elsewhere, "
                    "use the editor tool, or `write_text(..., newline='\\n')` in a script.",
                )
            )
    return violations


def check_control_characters(root: Path, markdown: Sequence[Path]) -> list[Violation]:
    """A control character in a doc: a path whose backslashes a script or a JSON string read as
    escapes, so the command a reader copies is not the one written (plan 002's review)."""
    violations: list[Violation] = []
    for path in markdown:
        # Decoded, not read_text: universal newlines would make a lone carriage return a line end.
        text = path.read_bytes().decode("utf-8")
        for lineno, line in enumerate(text.split("\n"), start=1):
            if found := _CONTROL.search(line.removesuffix("\r")):
                violations.append(
                    Violation(
                        path.relative_to(root).as_posix(),
                        lineno,
                        "DOC-CONTROL",
                        f"the line holds the control character U+{ord(found.group()):04X}",
                        "Retype it with the editor tool, never through a string that reads "
                        "escapes; write paths with forward slashes.",
                    )
                )
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="Check the docs and the plans.").parse_args(argv)
    return run_check("check_docs", ROOT, check_repo)


if __name__ == "__main__":
    sys.exit(main())
