"""The held-out split: by item, about 30%, stratified by language and kind, from a salted order;
new items placed with every committed item keeping its side (`--keep`); the committed
`split.json` is fresh (`split --check`, or `--check --keep` once kept), and a stale one fails."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from ole5_voice.evals import split
from ole5_voice.evals.items import EVALS, GoldenSetError, load_items
from ole5_voice.evals.models import Item, Language, Split, SplitFile
from ole5_voice.evals.split import DEFAULT_SALT, load_split, place_new, split_items
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


def test_new_items_are_placed_and_every_committed_item_keeps_its_side(tmp_path: Path) -> None:
    old = _items(("saudi", "request", 10))
    committed = SplitFile(salt="made-up", items=split_items(old, "made-up"))
    moved = Item.model_validate(old[0].model_dump() | {"kind": "noise"})  # its stratum changed
    new = _items(("english", "stop_word", 4), ("msa", "request", 3))
    gone = old[-1]  # an item no longer in the set
    found = place_new([moved, *old[1:-1], *new], committed)
    assert all(found[i.id] == committed.items[i.id] for i in old[:-1])
    assert gone.id not in found and list(found) == sorted(found)
    assert {i.id: found[i.id] for i in new} == split_items(new, "made-up")
    assert len(_held({i.id: found[i.id] for i in new})) == 2  # 30% of the 7 new, by stratum

    evals = _evals(tmp_path / "evals", old)
    command = ["--evals", str(evals)]
    assert split.main([*command, "--keep"]) == 1  # nothing committed yet to keep
    assert split.main(command) == 0
    sides = load_split(evals / "split.json").items
    for item in new:
        (evals / "golden" / f"{item.id}.toml").write_text(dump_item(item), encoding="utf-8")
    (evals / "golden" / f"{moved.id}.toml").write_text(dump_item(moved), encoding="utf-8")
    assert split.main([*command, "--check", "--keep"]) == 1  # the new items are not placed
    assert split.main([*command, "--keep"]) == 0
    kept = load_split(evals / "split.json").items
    assert all(kept[i.id] == sides[i.id] for i in old) and len(kept) == 17
    assert split.main([*command, "--check", "--keep"]) == 0
    with pytest.raises(SystemExit) as refused:
        split.main([*command, "--keep", "--salt", "x"])
    assert refused.value.code == 2


def test_the_command_refuses_a_set_with_no_item_or_no_folder(tmp_path: Path) -> None:
    assert split.main(["--evals", str(_evals(tmp_path / "evals", []))]) == 1
    assert split.main(["--evals", str(tmp_path / "absent")]) == 1


def test_the_committed_split_is_fresh_and_covers_every_item() -> None:
    """The committed split, written whole or with new items placed by `--keep`, names each item
    once with its committed side, and about 30% of them are held out."""
    assert split.main(["--check", "--keep"]) == 0
    committed = load_split(EVALS / "split.json")
    items = load_items(EVALS / "golden")
    assert set(committed.items) == {item.id for item in items}
    held_out = len(_held(committed.items))
    assert 0.27 <= held_out / len(items) <= 0.33


def _knowledge(folder: Path, sides: Mapping[str, Split]) -> None:
    """Made-up knowledge items under `folder`, each on the side `sides` gives."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, side in sides.items():
        language = "msa" if name.endswith("m") else "saudi"
        (folder / f"{name}.toml").write_text(
            f'id = "{name}"\nsplit = "{side}"\nkind = "none"\nneeds_search = true\n'
            'key_facts = ["says so", "invents none"]\nnotes = "a made-up item"\n'
            f'[[variants]]\nlanguage = "{language}"\ntext = "{name} one"\n'
            f'[[variants]]\nlanguage = "english"\ntext = "{name} two"\n',
            encoding="utf-8",
        )


def test_the_knowledge_sets_split_is_only_kept(tmp_path: Path) -> None:
    """`--knowledge` keeps the knowledge set's committed split: an item added is placed by
    `place_new` with the committed salt, every earlier item keeping its side, and `--check
    --keep` fails until it is written; the split is never written whole."""
    evals = tmp_path / "evals"
    folder = evals / "knowledge"
    old: dict[str, Split] = {f"q{n:02}_old": "held-out" if n < 3 else "dev" for n in range(10)}
    _knowledge(folder, old)
    command = ["--evals", str(evals), "--knowledge"]
    assert split.main([*command, "--keep"]) == 1  # nothing committed to keep
    committed = SplitFile(salt="made-up", items=old)
    (folder / "split.json").write_text(split.dump_split(committed), encoding="utf-8")
    assert split.main([*command, "--check", "--keep"]) == 0
    new: dict[str, Split] = {f"q{n:02}_newm": "dev" for n in range(10, 14)}
    _knowledge(folder, new)
    assert split.main([*command, "--check", "--keep"]) == 1
    assert split.main([*command, "--keep"]) == 0
    kept = load_split(folder / "split.json")
    assert kept.salt == "made-up"
    assert {name: kept.items[name] for name in old} == old  # no earlier item moved
    placed = {name: kept.items[name] for name in new}
    assert sorted(placed.values()) == ["dev", "dev", "dev", "held-out"]  # 30% of the four
    assert split.main([*command, "--check", "--keep"]) == 0
    for refused in ([*command], [*command, "--check"]):
        with pytest.raises(SystemExit) as stopped:
            split.main(refused)
        assert stopped.value.code == 2
