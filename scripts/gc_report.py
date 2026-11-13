"""Candidates for the next garbage-collection round: `uv run poe gc`, after its section on
whether a round is due (scripts/gc_due.py). Its settings are harness.toml's [gc].

Not a gate: every section lists candidates that need judgment, and the procedure for acting on
them is docs/harness/garbage-collection.md. Sections:

- duplicates: runs of [gc] min_tokens tokens or more repeated in the code outside tests/
  (imports, dunder methods, comments, and layout ignored), one line per run with every place
  it starts;
- unreferenced: top-level functions and classes, and the classes' methods, that nothing
  references (decorated ones, dunders, `main`, tests, AST visitors, and [gc] hooks skipped);
- suppressions: `noqa`, `type: ignore`, `pragma: no cover`, and `fmt: skip`, per file, and
  every `noqa` without a reason;
- size: modules above [gc] size_watch lines (the limit is [modules] max_lines);
- paths: file paths named in the living docs and the code that do not resolve;
- names: code names in backticks in the living docs that appear nowhere in the code (a cheap
  sign of a doc that no longer matches it).
The last two are scripts/gc_docs.py's, which says what they read and skip.
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

from scripts.gc_docs import comments, doc_sections
from scripts.harness_config import GcConfig, HarnessConfig, load_or_report

ROOT = Path(__file__).resolve().parents[1]
SUPPRESSIONS = ("# noqa", "# type: ignore", "# pragma: no cover", "# fmt: skip")
_NOQA_WITHOUT_REASON = re.compile(r"# noqa(?::\s*[A-Z]+\d+(?:,\s*[A-Z]+\d+)*)?\s*$")
_SKIPPED_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}
    | {tokenize.ENCODING, tokenize.ENDMARKER}
)
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


@dataclass(frozen=True)
class Run:
    """A repeated run: every place it starts, and its length, which can differ from one pair of
    places to another (each pair runs on as long as its two copies agree)."""

    shortest: int
    longest: int
    places: tuple[str, ...]  # path:line, by path and then line
    pairs: int  # the pairs of places that repeat it (`duplicates` lists each)


def _pairs_by_start(sources: dict[str, str], min_tokens: int) -> Iterable[list[Duplicate]]:
    """For each run of `min_tokens` tokens that starts a repeat, the pairs of places where it
    does (an empty list when none does)."""
    streams = {name: code_tokens(text) for name, text in sources.items()}
    windows: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    for name, stream in streams.items():
        texts = [t.text for t in stream]
        for start in range(len(texts) - min_tokens + 1):
            windows[tuple(texts[start : start + min_tokens])].append((name, start))
    for places in windows.values():
        found: list[Duplicate] = []
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
        yield found


def duplicates(sources: dict[str, str], min_tokens: int) -> list[Duplicate]:
    """Maximal token runs of at least `min_tokens` that occur in two places, longest first: one
    entry per pair of places (`poe quality` counts these)."""
    found = [pair for pairs in _pairs_by_start(sources, min_tokens) for pair in pairs]
    return sorted(found, key=lambda d: (-d.tokens, d.first, d.second))


def repeated_runs(sources: dict[str, str], min_tokens: int) -> list[Run]:
    """The pairs of `duplicates` gathered by the run they start with: one entry per repeated
    run, with every place it starts, longest first (what `poe gc` prints)."""
    runs = []
    for pairs in _pairs_by_start(sources, min_tokens):
        if pairs:
            places = sorted({p for d in pairs for p in (d.first, d.second)}, key=_by_line)
            lengths = [d.tokens for d in pairs]
            runs.append(Run(min(lengths), max(lengths), tuple(places), len(pairs)))
    return sorted(runs, key=lambda r: (-r.longest, r.places))


def _by_line(place: str) -> tuple[str, int]:
    path, line = place.rsplit(":", 1)
    return path, int(line)


def _length(run: Run) -> str:
    """`30`, or `30 to 34` when its pairs of places run on for different lengths."""
    if run.shortest == run.longest:
        return str(run.longest)
    return f"{run.shortest} to {run.longest}"


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
        for number, comment in comments(text):
            for kind in SUPPRESSIONS:
                if kind in comment:
                    found[kind] += 1
            if _NOQA_WITHOUT_REASON.search(comment):
                unexplained.append(f"{name}:{number}")
        if found:
            counts[name] = found
    return counts, unexplained


def large_modules(sources: dict[str, str], watch: int) -> list[tuple[int, str]]:
    sizes = [(len(text.splitlines()), name) for name, text in sources.items()]
    return sorted(((size, name) for size, name in sizes if size > watch), reverse=True)


def report(root: Path, config: HarnessConfig) -> str:
    gc: GcConfig = config.gc
    dirs = (*config.product_dirs, *config.arch.support_dirs)
    code = python_sources(root, dirs)
    product = {n: t for n, t in code.items() if not n.startswith("tests/")}
    lines = ["# Garbage-collection candidates", ""]
    runs = repeated_runs(product, gc.min_tokens)
    pairs = sum(r.pairs for r in runs)
    lines += [
        f"## Duplicates ({len(runs)} runs of {gc.min_tokens}+ tokens outside tests/, "
        f"in {pairs} pairs of places)"
    ]
    lines += [f"- {_length(r)} tokens: {' = '.join(r.places)}" for r in runs] or ["- none"]
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
    lines += doc_sections(root, config, code)
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
