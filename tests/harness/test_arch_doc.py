"""ARCH-DOC (scripts/arch_doc.py): the architecture doc's layer table and harness.toml agree,
row by row, on the synthetic project of support.py."""

from __future__ import annotations

from pathlib import Path

from scripts.arch_doc import layer_table
from scripts.check_architecture import ROOT, check_repo
from scripts.harness_config import load_config
from tests.harness.support import ARCHITECTURE, config, write


def _problems(tmp_path: Path, doc: str) -> list[tuple[int, str]]:
    loaded = config(tmp_path)
    write(tmp_path, {"src/app/__init__.py": "", "ARCHITECTURE.md": doc})
    violations, _ = check_repo(tmp_path, loaded)
    return sorted((v.line, v.problem) for v in violations if v.rule == "ARCH-DOC")


def test_a_table_that_matches_the_config_passes(tmp_path: Path) -> None:
    assert _problems(tmp_path, ARCHITECTURE) == []


def test_naming_a_layer_in_prose_is_not_enough(tmp_path: Path) -> None:
    prose = "Layers: core, domain, adapters, services, api.\n"
    assert _problems(tmp_path, prose) == [(1, "the layer table is missing")]


def test_a_layer_without_a_row_and_a_row_without_a_layer(tmp_path: Path) -> None:
    doc = ARCHITECTURE.replace("| `domain` |", "| `rules` |")
    assert _problems(tmp_path, doc) == [
        (3, "layer 'domain' of harness.toml has no row in the layer table"),
        (6, "the layer table has a row for 'rules', which is not in [layers]"),
    ]


def test_imports_and_owned_libraries_must_match(tmp_path: Path) -> None:
    doc = ARCHITECTURE.replace("| core, domain, adapters |", "| core, domain |").replace(
        "`sqlite3`, `httpx`", "`sqlite3`"
    )
    owns = "layer 'adapters' owns [httpx, sqlite3] in harness.toml's [[owners]], but its row says"
    imports = "layer 'services' may import [adapters, core, domain] in harness.toml, but its row"
    assert _problems(tmp_path, doc) == [
        (7, f"{owns} [sqlite3]"),
        (8, f"{imports} says [core, domain]"),
    ]


def test_a_layer_listed_twice_is_reported_once(tmp_path: Path) -> None:
    doc = ARCHITECTURE.replace(
        "| `api` |", "| `core` | Again | none | `logging`, `structlog` |\n| `api` |"
    )
    assert _problems(tmp_path, doc) == [(9, "layer 'core' has two rows in the layer table")]


def test_a_doc_turned_off_or_missing_is_not_read(tmp_path: Path) -> None:
    loaded = config(tmp_path)
    write(tmp_path, {"src/app/__init__.py": ""})
    violations, _ = check_repo(tmp_path, loaded)
    assert [v for v in violations if v.rule == "ARCH-DOC"] == []


def test_the_table_ends_at_the_first_line_outside_it() -> None:
    found = layer_table(
        "| Layer | May import | Owns |\n| --- | --- | --- |\n| `a` | b | |\nx\n| c |\n"
    )
    assert found is not None
    header, rows = found
    assert (header, [(r.layer, r.imports, r.owns) for r in rows]) == (
        1,
        [("a", frozenset({"b"}), frozenset())],
    )


def test_this_repositorys_table_matches_its_config() -> None:
    violations, _ = check_repo(ROOT, load_config(ROOT))
    assert [str(v) for v in violations if v.rule == "ARCH-DOC"] == []
