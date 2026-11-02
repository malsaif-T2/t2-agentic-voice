"""No item in the product (evaluation.md, "No item in the product"): no item's reference, and no
line of the script, appears as whole words in a string constant or a text file under
`packages/`, `apps/*/src` or `examples/`, except a text of `allowed_in_source.toml`, which grows
only by the owner's ruling. A self-test shows the search finds pasted text.

Both sides are folded before they are compared, into the form the scorers compare (the
library's `scored_form`: `normalize_arabic`, then `normalize_digits`), so the search finds what a
verdict would match. An underscore stays part of a word, so a label such as `stop_word` never
holds the word `stop`. Comments are not searched: a string is what a prompt, a message or a page
is made of.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Collection, Iterator, Mapping, Sequence
from datetime import date
from pathlib import Path

from ole5_voice.evals.items import EVALS, load_items, read_toml
from ole5_voice.evals.takes import Script
from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice.domain.scoring import scored_form
from t2_agentic_voice.languages import normalize_digits

ROOT = Path(__file__).resolve().parents[3]
SCANNED = [ROOT / "packages", *sorted((ROOT / "apps").glob("*/src")), ROOT / "examples"]
PYTHON = {".py", ".pyi"}
TEXT = {".md", ".toml", ".json", ".txt", ".js", ".mjs", ".html", ".css", ".cfg", ".ini"}
TEXT |= {".yaml", ".yml", ".rst", ".csv", ".jsonl", ".svg"}
# The library's characterization table of its normalizer: each row's input, and what the
# normalizer makes of it.
TABLE = ROOT / "tests" / "t2_agentic_voice" / "fixtures" / "arabic_normalizer_characterization.json"


def fold(text: str) -> str:
    """`text` in the one form both sides are compared in, the scorers' (`scored_form`), with an
    underscore kept as a word's part: each stretch between two underscores folded on its own."""
    return "_".join(scored_form(part) for part in text.split("_"))


class Allowed(BaseModel):
    """One entry of `allowed_in_source.toml`: a text, why, and the owner's ruling."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    said: str = Field(min_length=1)
    on: date


class AllowList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: tuple[Allowed, ...] = ()


def allowed(path: Path) -> set[str]:
    with path.open("rb") as file:
        return {fold(entry.text) for entry in AllowList.model_validate(tomllib.load(file)).allowed}


def references(evals: Path) -> dict[str, str]:
    """Every reference of every item, its alternatives and the script's lines, folded, each with
    where it comes from."""
    found: dict[str, str] = {}
    for item in load_items(evals / "golden"):
        for text in (item.text, *item.alternatives):
            found.setdefault(fold(text), f"item {item.id}")
        for variant in item.variants:
            found.setdefault(fold(variant.reference), f"variant {variant.id}")
    for line in read_toml(evals / "script.toml", Script).lines:
        found.setdefault(fold(line.text), f"script line {line.id}")
    found.pop("", None)
    return found


def strings(path: Path) -> Iterator[tuple[int, str]]:
    """A Python module's string constants (docstrings and f-strings' parts among them), each
    with its line; a text file's whole text, from its first line."""
    source = path.read_text(encoding="utf-8")
    if path.suffix in TEXT:
        yield 1, source
        return
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def find_pasted(
    base: Path, roots: Sequence[Path], found: Mapping[str, str], exempt: Collection[str] = ()
) -> list[str]:
    """Each place under `roots` where a reference sits as whole words, as `file:line: where`,
    the file named from `base`."""
    wanted = sorted(set(found) - set(exempt), key=len, reverse=True)
    if not wanted:
        return []
    words = re.compile(r"(?<!\w)(" + "|".join(re.escape(text) for text in wanted) + r")(?!\w)")
    hits = []
    for root in roots:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if "__pycache__" in path.parts or path.suffix not in PYTHON | TEXT:
                continue
            for line, text in strings(path):
                for match in words.finditer(fold(text)):
                    name = path.relative_to(base).as_posix()
                    hits.append(f"{name}:{line}: {found[match.group(1)]}")
    return hits


def test_no_item_appears_in_the_source() -> None:
    found = references(EVALS)
    assert len(found) > 80  # the talk-over's and the script's, so the search has its terms
    assert {"stop", "wait", "okay", "yeah"} <= set(found)
    assert find_pasted(ROOT, SCANNED, found, allowed(EVALS / "allowed_in_source.toml")) == []


def test_the_allow_list_starts_empty_and_names_the_owners_ruling(tmp_path: Path) -> None:
    assert allowed(EVALS / "allowed_in_source.toml") == set()
    path = tmp_path / "allowed.toml"
    path.write_text(
        '[[allowed]]\ntext = "Okay!"\nreason = "a made-up case"\nsaid = "made up"\n'
        "on = 2026-11-01\n",
        encoding="utf-8",
    )
    assert allowed(path) == {"okay"}


def _tree(root: Path, files: Mapping[str, str]) -> list[Path]:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return [root / "packages", root / "apps" / "a" / "src", root / "examples"]


def test_the_search_finds_a_pasted_reference_in_any_form(tmp_path: Path) -> None:
    found = {fold("كيف أؤرشف مراسلة في النظام؟"): "item s01", fold("stop"): "item k05"}
    files = {
        "packages/lib/a.py": '"""Say STOP!"""\n',  # a docstring, in upper case
        "packages/lib/b.py": 'x = f"{1} كيف اؤرشف مراسلة في النظام"\n',  # an f-string, no hamza
        "apps/a/src/app/page.html": "<button>Stop</button>",  # a page's label
        "examples/demo/README.md": "Then say «stop».",
        "packages/lib/c.py": "y = '\\u0643\\u064a\\u0641 \\u0623\\u0624\\u0631\\u0634\\u0641"
        " \\u0645\\u0631\\u0627\\u0633\\u0644\\u0629 \\u0641\\u064a \\u0627\\u0644\\u0646\\u0638"
        "\\u0627\\u0645'\n",  # written with escapes, as the library's tables are
    }
    hits = find_pasted(tmp_path, _tree(tmp_path, files), found)
    assert sorted(hits) == [
        "apps/a/src/app/page.html:1: item k05",
        "examples/demo/README.md:1: item k05",
        "packages/lib/a.py:1: item k05",
        "packages/lib/b.py:1: item s01",
        "packages/lib/c.py:1: item s01",
    ]


def test_the_search_takes_only_whole_words_and_strings(tmp_path: Path) -> None:
    found = {fold("stop"): "item k05", fold("okay"): "item b09"}
    files = {
        "packages/lib/a.py": (
            '# say stop in a comment: not a string\nKIND = "stop_word"\n'
            'B = "stopped, unstoppable"\nC = "k05_stop"\nD = b"okay"\n'
        ),
        "packages/lib/__pycache__/a.cpython-312.pyc": "okay",
        "packages/lib/data.bin": "okay",
        "apps/a/src/app/x.py": 'E = "OK, then"\n',
    }
    assert find_pasted(tmp_path, _tree(tmp_path, files), found) == []
    exempt = {fold("stop")}
    files = {"packages/lib/f.py": 'F = "stop"\n'}
    assert find_pasted(tmp_path, _tree(tmp_path, files), found, exempt) == []
    assert find_pasted(tmp_path, _tree(tmp_path, files), found) == ["packages/lib/f.py:1: item k05"]
    assert find_pasted(tmp_path, _tree(tmp_path, files), {}) == []


def test_the_fold_reads_each_row_of_the_normalizers_table_as_the_scorers_do() -> None:
    """Each row of the library's characterization table folds to what the table says the
    normalizer makes of it, its digits then read; only an underscore is kept, inside a word."""
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["rows"]
    assert len(rows) > 20
    for row in rows:
        if "_" not in row["input"]:
            assert fold(row["input"]) == normalize_digits(row["normalize"]), row["note"]
    assert (fold("stop_word"), fold("k05_واحد")) == ("stop_word", "k05_1")
    assert fold("say STOP!_now") == "say stop_now"
