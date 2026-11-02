"""The garbage-collection report finds what it claims to find, and nothing it should ignore."""

from __future__ import annotations

from pathlib import Path

from scripts.gc_report import (
    ROOT,
    code_tokens,
    comments_and_docstrings,
    duplicates,
    large_modules,
    report,
    suppressions,
    unknown_names,
    unreferenced,
    unresolved_paths,
)
from scripts.harness_config import load_config
from tests.harness.support import config, write

SHARED = """
def total(rows):
    result = 0
    for row in rows:
        if row.amount is not None and row.currency == "EUR":
            result += row.amount * row.rate
    return round(result, 2)
"""


def test_a_copied_block_is_reported_once_with_both_places() -> None:
    sources = {"a.py": "import os\n" + SHARED, "b.py": "x = 1\n\n" + SHARED.replace("total", "t")}
    [found] = duplicates(sources, min_tokens=20)
    assert (found.first, found.second) == ("a.py:3", "b.py:4")
    assert found.tokens >= 30


def test_imports_and_dunder_methods_are_not_duplication() -> None:
    imports = "from a.b import (\n    one,\n    two,\n    three,\n    four,\n    five,\n)\n"
    dunder = "class C:\n    def __exit__(self, exc_type, exc, traceback) -> None:\n        pass\n"
    assert code_tokens(imports) == []
    assert [t.text for t in code_tokens(dunder)] == ["class", "C", ":"]
    assert duplicates({"a.py": imports + dunder, "b.py": imports + dunder}, min_tokens=4) == []


def test_unreferenced_definitions_skip_what_frameworks_call() -> None:
    sources = {
        "lib.py": (
            "def used(): ...\ndef unused(): ...\n@router.get('/x')\ndef route(): ...\n"
            "def main(): ...\nclass Store:\n    def orphan(self): ...\n    def __len__(self): ...\n"
            "class Handler(logging.Handler):\n    def emit(self, record): ...\n"  # a hook
        ),
        "app.py": "from lib import used, Handler\nused()\nHandler()\n",
    }
    assert unreferenced(sources, ["lib.py"], hooks=frozenset({"emit"})) == [
        "lib.py:2 unused",
        "lib.py:6 Store",
        "lib.py:7 orphan",
    ]


def test_async_definitions_are_read_as_the_others_are() -> None:
    """An unused async method is reported, and an async dunder is boilerplate, not duplication."""
    sources = {
        "lib.py": "class Client:\n    async def fetch(self): ...\n    async def gone(self): ...\n",
        "app.py": "from lib import Client\nClient().fetch()\n",
    }
    assert unreferenced(sources, ["lib.py"]) == ["lib.py:3 gone"]
    dunder = (
        "class C:\n    async def __aexit__(self, exc_type, exc, traceback) -> None:\n        pass\n"
    )
    assert [t.text for t in code_tokens(dunder)] == ["class", "C", ":"]


def test_suppressions_are_counted_and_noqa_needs_a_reason() -> None:
    source = (
        "a = 1  # noqa: S105 - a documented dev value\nb = 2  # noqa: S105\nc = 3  # fmt: skip\n"
    )
    counts, unexplained = suppressions({"m.py": source})
    assert counts["m.py"]["# noqa"] == 2
    assert counts["m.py"]["# fmt: skip"] == 1
    assert unexplained == ["m.py:2"]


def test_only_comments_suppress() -> None:
    """A marker in a string (the tools' own constants, a test's fixture) suppresses nothing."""
    source = (
        'KINDS = ("# noqa", "# type: ignore")\nFIXTURE = "x = 1  # noqa"\nd = 4  # type: ignore\n'
    )
    counts, unexplained = suppressions({"m.py": source})
    assert dict(counts["m.py"]) == {"# type: ignore": 1}
    assert unexplained == []


def test_size_watch_lists_large_modules_largest_first() -> None:
    sources = {"small.py": "x = 1\n", "big.py": "x = 1\n" * 12, "bigger.py": "x = 1\n" * 15}
    assert large_modules(sources, watch=10) == [(15, "bigger.py"), (12, "big.py")]


def test_paths_that_do_not_resolve_are_reported(tmp_path: Path) -> None:
    write(tmp_path, {"docs/real.md": ""})
    texts = {
        "notes.md": "See docs/real.md and docs/gone.md, and var/app/cache.json.\n",
        "template.md": "Create `active/NNN-short-slug.md`.\n",  # a placeholder, not a path
    }
    found = unresolved_paths(tmp_path, texts, bases=("",), ignored=("var/",))
    assert found == ["notes.md:1 docs/gone.md"]


def test_paths_of_every_text_kind_and_in_a_dot_folder_are_checked(tmp_path: Path) -> None:
    write(tmp_path, {".github/workflows/ci.yml": "", "web/app.js": ""})
    named = (
        ".github/workflows/ci.yml .github/workflows/gone.yml web/app.js web/gone.js web/index.html "
        "web/site.css evals/history.jsonl conf/settings.yaml notes/todo.txt ../up/a.md"
    )
    found = unresolved_paths(tmp_path, {"notes.md": named}, bases=("",), ignored=())
    assert [f.split(" ", 1)[1] for f in found] == [
        ".github/workflows/gone.yml",
        "web/gone.js",
        "web/index.html",
        "web/site.css",
        "evals/history.jsonl",
        "conf/settings.yaml",
        "notes/todo.txt",
    ]  # a path that climbs out with ../ is a link, which `poe docs` checks


def test_names_the_docs_cite_must_be_in_the_code() -> None:
    code = "def load_orders(): ...\nclass OrderBook: ..."
    docs = {
        "docs/a.md": "Uses `load_orders()` and `OrderBook.add`, not `old_helper`.\n",
        "docs/b.md": "Plain words in backticks: `poe`, `dev`, `AsyncClient`.\n",
        # Another library's names: a last part, a whole name, or under a dotted prefix.
        "docs/c.md": "`httpx.AsyncClient`, `vendor.FrameStats`, `vendor.sub.Frame_Out`.\n",
    }
    foreign = frozenset({"AsyncClient", "vendor.FrameStats", "vendor.sub"})
    assert unknown_names(code, docs, foreign) == ["docs/a.md:1 old_helper"]
    assert unknown_names(code, {"d.md": "`vendors.Frame_Out`"}, foreign) == [
        "d.md:1 vendors.Frame_Out"
    ]


def test_in_tests_only_comments_and_docstrings_name_files() -> None:
    source = (
        '"""Reads docs/real.md."""\n\nFIXTURE = "made/up.md"  # see docs/notes.md\n\n'
        'def test_x() -> None:\n    """Of src/x.py,\n    and src/y.py."""\n    open("a/b.md")\n'
    )
    kept = comments_and_docstrings(source).splitlines()
    assert len(kept) == len(source.splitlines())
    assert [n for n, line in enumerate(kept, start=1) if line] == [1, 3, 6, 7]
    assert "made/up.md" not in kept[2] and "a/b.md" not in "".join(kept)


def test_the_report_runs_on_a_small_project(tmp_path: Path) -> None:
    loaded = config(tmp_path)
    write(
        tmp_path,
        {
            "src/app/__init__.py": "",
            "src/app/core/a.py": SHARED,
            "src/app/domain/b.py": SHARED,
            "docs/a.md": "See `missing_name` in src/app/core/gone.py.\n",
            # History keeps the names and paths of its time ([docs] historical).
            "docs/plans/completed/001-old.md": "Once `old_helper` in src/app/old.py.\n",
            # A planned doc's are counted ([gc] planned_docs).
            "docs/design/plan.md": "`future_api` in src/app/api/next.py, `other_one`.\n",
            "tests/test_a.py": '"""Of src/app/core/lost.py."""\nFIXTURE = "src/app/made_up.py"\n',
            "pyproject.toml": "",
        },
    )
    text = report(tmp_path, loaded)
    assert "## Duplicates (1 runs of 20+ tokens" in text
    assert (
        "## Unresolved paths (2)\n- tests/test_a.py:1 src/app/core/lost.py\n"
        "- docs/a.md:1 src/app/core/gone.py\n"
        "- docs/design/plan.md: 1 more, planned ([gc] planned_docs)\n"
    ) in text
    assert "## Names in docs that the code does not have (1)\n- docs/a.md:1 missing_name\n" in text
    assert "- docs/design/plan.md: 2 more, planned ([gc] planned_docs)\n" in text


def test_the_report_runs_on_this_repository() -> None:
    text = report(ROOT, load_config(ROOT))
    for section in ("Duplicates", "Unreferenced", "Suppressions", "Modules above", "Unresolved"):
        assert f"## {section}" in text
    assert "## Names in docs" in text
