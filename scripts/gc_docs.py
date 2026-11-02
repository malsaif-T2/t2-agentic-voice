"""The doc-side sections of `poe gc`'s report (scripts/gc_report.py): file paths named in the
living docs and the code that do not resolve, and code names the living docs cite that the code
does not have. Their settings are harness.toml's [gc] path_bases, path_ignored, foreign_names,
name_files, and planned_docs, and [docs] historical.

History keeps the paths and names of its time, so it is not read. A doc of planned code gets one
count per section instead of a list, and in tests/ only comments and docstrings are read: a
string there is a fixture's made-up file.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from scripts.doc_text import markdown_files
from scripts.harness_config import HarnessConfig

# A relative path: folders, then a file of a text kind. A folder may be hidden (`.github/`);
# a path that climbs out (`../`) is a link, which `poe docs` resolves.
_PATH = re.compile(
    r"(?<![\w./{-])((?:\.?[A-Za-z_][\w.-]*/)+[\w-]+"
    r"\.(?:py|md|toml|jsonl|json|yaml|yml|js|html|css|txt))\b"
)
_PLACEHOLDER = "NNN"  # a template's placeholder (`active/NNN-short-slug.md`), not a path
_FIXTURE_FILES = ("tests/harness/",)  # the harness's tests name imaginary files
_NAME = re.compile(r"`([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?:\(\))?`")


def comments(source: str) -> Iterable[tuple[int, str]]:
    """(line, text) of each comment."""
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string


def unresolved_paths(
    root: Path, texts: dict[str, str], bases: Sequence[str], ignored: Sequence[str]
) -> list[str]:
    """`path:line ref` for each named file path that exists under none of `bases`, nor beside
    the file that names it."""
    missing = []
    for name, text in texts.items():
        if name.startswith(_FIXTURE_FILES):
            continue  # the harness's tests name imaginary files
        for number, line in enumerate(text.splitlines(), start=1):
            for match in _PATH.finditer(line):
                ref = match.group(1)
                if ref.startswith(tuple(ignored)) or _PLACEHOLDER in ref:
                    continue
                here = str(Path(name).parent)
                if not any((root / base / ref).exists() for base in (*bases, here)):
                    missing.append(f"{name}:{number} {ref}")
    return missing


def unknown_names(
    code: str, docs: dict[str, str], foreign: frozenset[str] = frozenset()
) -> list[str]:
    """`doc:line name` for each code-like name in backticks (an underscore or an inner capital,
    four characters or more) that `code` never mentions. A `foreign` name is another library's:
    its last part, or the whole name, or a dotted prefix of it (`pipecat` for `pipecat.x.y`)."""
    missing = []
    for name, text in docs.items():
        for number, line in enumerate(text.splitlines(), start=1):
            for match in _NAME.finditer(line):
                full = match.group(1)
                last = full.split(".")[-1]
                code_like = "_" in last or any(c.isupper() for c in last[1:])
                theirs = {full, last} & foreign or any(full.startswith(f"{f}.") for f in foreign)
                if len(last) >= 4 and code_like and not theirs and last not in code:
                    missing.append(f"{name}:{number} {full}")
    return missing


def comments_and_docstrings(source: str) -> str:
    """The module with only its comments and docstrings kept, each on its own line: in tests, a
    path in a string is a fixture's made-up file."""
    lines = source.splitlines()
    kept = [""] * len(lines)
    for number, comment in comments(source):
        kept[number - 1] = comment
    for node in ast.walk(ast.parse(source)):
        documented = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        if isinstance(node, documented) and ast.get_docstring(node) is not None:
            first = node.body[0]
            for number in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                kept[number - 1] = lines[number - 1]
    return "".join(f"{line}\n" for line in kept)


def _planned(found: list[str]) -> list[str]:
    """One line per planned doc ([gc] planned_docs): how many entries it has."""
    counts = Counter(entry.split(":", 1)[0] for entry in found)
    return [f"- {doc}: {n} more, planned ([gc] planned_docs)" for doc, n in sorted(counts.items())]


def doc_sections(root: Path, config: HarnessConfig, code: dict[str, str]) -> list[str]:
    """The report's last two sections, given the code (path -> text) it reads."""
    gc = config.gc
    docs = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in markdown_files(root)
    }
    living = {n: t for n, t in docs.items() if not n.startswith(config.docs.historical)}
    planned = {n: t for n, t in living.items() if n in gc.planned_docs}
    current = {n: t for n, t in living.items() if n not in gc.planned_docs}
    cited = {
        n: comments_and_docstrings(t) if n.startswith("tests/") else t for n, t in code.items()
    }
    lines: list[str] = []
    bases = (*gc.path_bases, *config.product_dirs)
    paths = unresolved_paths(root, cited | current, bases, gc.path_ignored)
    lines += ["", f"## Unresolved paths ({len(paths)})"]
    lines += [f"- {p}" for p in paths] or ["- none"]
    lines += _planned(unresolved_paths(root, planned, bases, gc.path_ignored))
    named = [p for pattern in gc.name_files for p in sorted(root.glob(pattern)) if p.is_file()]
    every = "\n".join([*code.values(), *(p.read_text(encoding="utf-8") for p in named)])
    names = unknown_names(every, current, gc.foreign_names)
    lines += ["", f"## Names in docs that the code does not have ({len(names)})"]
    lines += [f"- {n}" for n in names] or ["- none"]
    lines += _planned(unknown_names(every, planned, gc.foreign_names))
    return lines
