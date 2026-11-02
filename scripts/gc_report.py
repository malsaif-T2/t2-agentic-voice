"""Candidates for the next garbage-collection round: `uv run poe gc`, after its section on
whether a round is due (scripts/gc_due.py). Its settings are harness.toml's [gc].

Not a gate: every section lists candidates that need judgment, and the procedure for acting on
them is docs/harness/garbage-collection.md. Sections:

- duplicates: runs of [gc] min_tokens tokens or more repeated in the code outside tests/
  (imports, dunder methods, comments, and layout ignored);
- unreferenced: top-level functions and classes, and the classes' methods, that nothing
  references (decorated ones, dunders, `main`, tests, AST visitors, and [gc] hooks skipped);
- suppressions: `noqa`, `type: ignore`, `pragma: no cover`, and `fmt: skip`, per file, and
  every `noqa` without a reason;
- size: modules above [gc] size_watch lines (the limit is [modules] max_lines);
- paths: file paths named in the living docs and the code that do not resolve (in tests/, only
  comments and docstrings are read: a string there is a fixture's made-up file);
- names: code names in backticks in the living docs that appear nowhere in the code (a cheap
  sign of a doc that no longer matches it).
History ([docs] historical) keeps the paths and names of its time, so it is not read; a doc of
planned code ([gc] planned_docs) gets one count per section instead of a list.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.doc_text import markdown_files
from scripts.harness_config import GcConfig, HarnessConfig, load_or_report

ROOT = Path(__file__).resolve().parents[1]
SUPPRESSIONS = ("# noqa", "# type: ignore", "# pragma: no cover", "# fmt: skip")
_NOQA_WITHOUT_REASON = re.compile(r"# noqa(?::\s*[A-Z]+\d+(?:,\s*[A-Z]+\d+)*)?\s*$")
_SKIPPED_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
    | {tokenize.ENCODING, tokenize.ENDMARKER}
)
# A relative path: folders, then a file of a text kind. A folder may be hidden (`.github/`);
# a path that climbs out (`../`) is a link, which `poe docs` resolves.
_PATH = re.compile(
    r"(?<![\w./{-])((?:\.?[A-Za-z_][\w.-]*/)+[\w-]+"
    r"\.(?:py|md|toml|jsonl|json|yaml|yml|js|html|css|txt))\b"
)
_PLACEHOLDER = "NNN"  # a template's placeholder (`active/NNN-short-slug.md`), not a path
_FIXTURE_FILES = ("tests/harness/",)  # the harness's tests name imaginary files
_NAME = re.compile(r"`([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?:\(\))?`")
# A function is a `def` or an `async def`: every rule here reads both (an async one was missed
# twice in this file, plan 004).
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class Token:
    text: str
    line: int


@dataclass(frozen=True)
class Duplicate:
    tokens: int
    first: str  # path:line
    second: str


def python_files(root: Path, dirs: Sequence[str]) -> list[Path]:
    return sorted(p for d in dirs for p in (root / d).rglob("*.py") if "__pycache__" not in p.parts)


def python_sources(root: Path, dirs: Sequence[str]) -> dict[str, str]:
    """path from the root -> text, for every Python module under `dirs`."""
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in python_files(root, dirs)
    }


def code_tokens(source: str) -> list[Token]:
    """Significant tokens, without imports and dunder methods (`__exit__` and the like): the
    same import block or protocol boilerplate in two modules is not duplication."""
    tree = ast.parse(source)
    ignored = {
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        or (isinstance(node, _FUNCTIONS) and node.name.startswith("__"))
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1)
    }
    return [
        Token(tok.string, tok.start[0])
        for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type not in _SKIPPED_TOKENS and tok.start[0] not in ignored
    ]


def duplicates(sources: dict[str, str], min_tokens: int) -> list[Duplicate]:
    """Maximal token runs of at least `min_tokens` that occur in two places, longest first."""
    streams = {name: code_tokens(text) for name, text in sources.items()}
    windows: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    for name, stream in streams.items():
        texts = [t.text for t in stream]
        for start in range(len(texts) - min_tokens + 1):
            windows[tuple(texts[start : start + min_tokens])].append((name, start))
    found: list[Duplicate] = []
    for places in windows.values():
        for i, (a_name, a) in enumerate(places):
            for b_name, b in places[i + 1 :]:
                one, two = streams[a_name], streams[b_name]
                if a_name == b_name and abs(a - b) < min_tokens:
                    continue  # overlapping windows of one repeated run
                if a and b and one[a - 1].text == two[b - 1].text:
                    continue  # not the start of the run
                length = min_tokens
                while (
                    a + length < len(one)
                    and b + length < len(two)
                    and one[a + length].text == two[b + length].text
                ):
                    length += 1
                found.append(
                    Duplicate(length, f"{a_name}:{one[a].line}", f"{b_name}:{two[b].line}")
                )
    return sorted(found, key=lambda d: (-d.tokens, d.first, d.second))


def unreferenced(
    sources: dict[str, str], candidates: Iterable[str], hooks: frozenset[str] = frozenset()
) -> list[str]:
    """`path:line name` for definitions in `candidates` files that no source references.

    Decorated functions (routes, fixtures, validators), dunders, `main`, tests, AST visitors,
    and `hooks` (methods a library calls on our subclasses) are skipped.
    """
    trees = {name: ast.parse(text) for name, text in sources.items()}
    used: set[str] = set()
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.alias):
                used.add(node.name.split(".")[-1])
    unused = []
    for name in candidates:
        for node, line in _definitions(trees[name], hooks):
            if node.name not in used:
                unused.append(f"{name}:{line} {node.name}")
    return unused


def _definitions(
    tree: ast.Module, hooks: frozenset[str]
) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, int]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            yield node, node.lineno
            members = [n for n in node.body if isinstance(n, _FUNCTIONS)]
            yield from ((n, n.lineno) for n in members if _plain(n, hooks))
        elif isinstance(node, _FUNCTIONS) and _plain(node, hooks):
            yield node, node.lineno


def _plain(node: ast.FunctionDef | ast.AsyncFunctionDef, hooks: frozenset[str]) -> bool:
    name = node.name
    return not (
        node.decorator_list
        or name.startswith(("__", "test_", "visit_"))
        or name in hooks
        or name == "main"
    )


def suppressions(sources: dict[str, str]) -> tuple[dict[str, Counter[str]], list[str]]:
    """Per-file counts of each suppression kind, and every `noqa` without a reason. Only
    comments count: a marker inside a string (a constant, a test's fixture) suppresses nothing."""
    counts: dict[str, Counter[str]] = {}
    unexplained = []
    for name, text in sources.items():
        found: Counter[str] = Counter()
        for number, comment in _comments(text):
            for kind in SUPPRESSIONS:
                if kind in comment:
                    found[kind] += 1
            if _NOQA_WITHOUT_REASON.search(comment):
                unexplained.append(f"{name}:{number}")
        if found:
            counts[name] = found
    return counts, unexplained


def _comments(source: str) -> Iterable[tuple[int, str]]:
    """(line, text) of each comment."""
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string


def large_modules(sources: dict[str, str], watch: int) -> list[tuple[int, str]]:
    sizes = [(len(text.splitlines()), name) for name, text in sources.items()]
    return sorted(((size, name) for size, name in sizes if size > watch), reverse=True)


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
    for number, comment in _comments(source):
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


def report(root: Path, config: HarnessConfig) -> str:
    gc: GcConfig = config.gc
    dirs = (*config.product_dirs, *config.arch.support_dirs)
    code = python_sources(root, dirs)
    product = {n: t for n, t in code.items() if not n.startswith("tests/")}
    docs = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in markdown_files(root)
    }
    living = {n: t for n, t in docs.items() if not n.startswith(config.docs.historical)}
    planned = {n: t for n, t in living.items() if n in gc.planned_docs}
    current = {n: t for n, t in living.items() if n not in gc.planned_docs}
    cited = {
        n: comments_and_docstrings(t) if n.startswith("tests/") else t for n, t in code.items()
    }
    lines = ["# Garbage-collection candidates", ""]
    found = duplicates(product, gc.min_tokens)
    lines += [f"## Duplicates ({len(found)} runs of {gc.min_tokens}+ tokens outside tests/)"]
    lines += [f"- {d.tokens} tokens: {d.first} = {d.second}" for d in found] or ["- none"]
    unused = unreferenced(code, sorted(product), gc.hooks)
    lines += ["", f"## Unreferenced definitions ({len(unused)})"]
    lines += [f"- {u}" for u in unused] or ["- none"]
    counts, unexplained = suppressions(code)
    totals: Counter[str] = sum(counts.values(), Counter())
    lines += ["", "## Suppressions", *(f"- `{kind}`: {totals[kind]}" for kind in SUPPRESSIONS)]
    lines += [f"- `noqa` without a reason: {u}" for u in unexplained]
    big = large_modules(code, gc.size_watch)
    lines += ["", f"## Modules above {gc.size_watch} lines ({len(big)})"]
    lines += [f"- {size} {name}" for size, name in big] or ["- none"]
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
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report garbage-collection candidates.")
    parser.parse_args(argv)
    config = load_or_report("gc_report", ROOT)
    if config is None:
        return 1
    print(report(ROOT, config), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
