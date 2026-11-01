"""The held-out split: by item, about 30%, stratified by language and kind, from a salted order;
the committed `split.json` is fresh (`split --check`), and a stale one fails."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from ole5_voice.evals import split
from ole5_voice.evals.items import EVALS, GoldenSetError, load_items
from ole5_voice.evals.models import Item, Language
from ole5_voice.evals.split import DEFAULT_SALT, load_split, split_items
from ole5_voice.evals.toml_write import dump_item

from tests.ole5_voice.evals import samples


def _items(*strata: tuple[Language, str, int]) -> list[Item]:
    """`n` made-up items of each language and kind, each with its own variant."""
    items = []
    for language, kind, n in strata:
        for i in range(n):
            name = f"{language[:2]}-{kind}-{i}"
            base = samples.item(name).model_dump()
            base |= {"language": language, "kind": kind, "variants": (samples.variant(name),)}
            items.append(Item.model_validate(base))
    return items


def _held(found: Mapping[str, str]) -> list[str]:
    return [item for item, side in found.items() if side == "held-out"]


def test_about_30_percent_of_the_items_are_held_out_by_stratum() -> None:
    items = _items(("saudi", "request", 10), ("english", "request", 7), ("msa", "stop_word", 3))
    found = split_items(items, salt="made-up")
    assert set(found) == {item.id for item in items}
    assert len(_held(found)) == 6  # 30% of 20
    by_stratum = {
        kind: sum(1 for i in items if i.id.startswith(kind) and found[i.id] == "held-out")
        for kind in ("sa-request", "en-request", "ms-stop_word")
    }
    assert by_stratum == {"sa-request": 3, "en-request": 2, "ms-stop_word": 1}


def test_the_items_left_over_go_to_the_largest_remainders() -> None:
    # 7 items: 30% is 2.1, so 2 held out; the strata hold 0.3, 0.6 and 1.2 of one, so the
    # stratum of four holds out one, and the one left over goes to the stratum of two.
    items = _items(("saudi", "request", 1), ("english", "request", 2), ("msa", "request", 4))
    found = split_items(items, salt="made-up")
    assert sorted(i[:2] for i in _held(found)) == ["en", "ms"]


def test_the_split_is_deterministic_and_moves_with_its_salt() -> None:
    items = _items(("saudi", "request", 20))
    first = split_items(items, salt="one")
    assert split_items(list(reversed(items)), salt="one") == first
    assert list(first) == sorted(first)
    others = [split_items(items, salt=f"salt-{n}") for n in range(5)]
    assert any(_held(other) != _held(first) for other in others)
    assert all(len(_held(other)) == 6 for other in others)
    with pytest.raises(ValueError, match="salt"):
        split_items(items, salt="")


def test_the_split_file_is_read_strictly(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    path.write_text(json.dumps({"salt": "s", "items": {"i1": "dev"}}), encoding="utf-8")
    assert load_split(path).items == {"i1": "dev"}
    for broken in ({"salt": "s", "items": {"i1": "test"}}, {"salt": "", "items": {"i1": "dev"}}):
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(GoldenSetError, match=re.escape("split.json")):
            load_split(path)


def _evals(folder: Path, items: list[Item]) -> Path:
    (folder / "golden").mkdir(parents=True)
    for item in items:
        (folder / "golden" / f"{item.id}.toml").write_text(dump_item(item), encoding="utf-8")
    return folder


def test_the_command_writes_the_split_and_checks_it(tmp_path: Path) -> None:
    items = _items(("saudi", "request", 6), ("english", "stop_word", 4))
    evals = _evals(tmp_path / "evals", items)
    command = ["--evals", str(evals)]
    assert split.main([*command, "--check"]) == 1  # nothing committed yet
    assert split.main(command) == 0
    written = load_split(evals / "split.json")
    assert written.salt == DEFAULT_SALT and len(_held(written.items)) == 3
    assert (evals / "split.json").read_bytes().endswith(b"}\n")
    assert split.main([*command, "--check"]) == 0
    assert split.main([*command, "--salt", "another"]) == 0
    assert load_split(evals / "split.json").salt == "another"
    assert split.main(command) == 0  # the committed salt is kept
    assert load_split(evals / "split.json").salt == "another"
    # An item's stratum changes: the committed split is stale until it is written again.
    moved = Item.model_validate(items[0].model_dump() | {"kind": "noise"})
    (evals / "golden" / f"{moved.id}.toml").write_text(dump_item(moved), encoding="utf-8")
    (evals / "golden" / "extra.toml").write_text(dump_item(samples.item("extra")), encoding="utf-8")
    assert split.main([*command, "--check"]) == 1
    with pytest.raises(SystemExit) as refused:
        split.main([*command, "--check", "--salt", "x"])
    assert refused.value.code == 2


def test_the_command_refuses_a_set_with_no_item_or_no_folder(tmp_path: Path) -> None:
    assert split.main(["--evals", str(_evals(tmp_path / "evals", []))]) == 1
    assert split.main(["--evals", str(tmp_path / "absent")]) == 1


def test_the_committed_split_is_fresh_and_covers_every_item() -> None:
    assert split.main(["--check"]) == 0
    committed = load_split(EVALS / "split.json")
    items = load_items(EVALS / "golden")
    assert set(committed.items) == {item.id for item in items}
    held_out = len(_held(committed.items))
    assert held_out == (3 * len(items) + 5) // 10
