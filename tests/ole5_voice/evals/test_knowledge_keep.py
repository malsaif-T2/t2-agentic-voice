"""The knowledge set's keep path (TD-114): `knowledge/split.json` keeps every item's side, the
first 64 as drafted; an item added later is placed by the golden set's `place_new`, so no kept
item moves; an item off its kept side, one the file does not name, a name no item has and
another salt are each named (ole5_voice/evals/knowledge_set.py)."""

from __future__ import annotations

from ole5_voice.evals.items import EVALS
from ole5_voice.evals.knowledge_set import (
    KEPT_FILE,
    KNOWLEDGE_DIR,
    SALT,
    load_knowledge_items,
)
from ole5_voice.evals.models import SplitFile
from ole5_voice.evals.split import load_split, place_new, split_items

from tests.ole5_voice.evals.knowledge_samples import an_item as _item
from tests.ole5_voice.evals.knowledge_samples import kept_as as _kept
from tests.ole5_voice.evals.knowledge_samples import made_up_set as _set
from tests.ole5_voice.evals.knowledge_samples import problems_in as _problems


def test_the_committed_split_keeps_every_items_side() -> None:
    """`knowledge/split.json` names every item with the side its file gives, under the set's
    salt; the 64 items drafted first are all in it (TD-114's keep path)."""
    kept = load_split(EVALS / KEPT_FILE)
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    assert kept.salt == SALT
    assert kept.items == {item.id: item.split for item in items}


# The `none` items added after the first 64 were drafted (the owner's Q13, 2026-11-07).
ADDED = (
    "q37_dark_mode",
    "q38_auto_reply",
    "q39_fingerprint_login",
    "q40_offline",
    "q41_notification_sound",
    "q42_password_expiry",
)


def test_the_items_added_later_were_placed_by_the_keep_rule() -> None:
    """The six `none` items added after the first 64 were placed by `place_new` against the
    split that froze those 64, so none of the 64 moved; each needs a search and expects no
    point, and each language the set holds fewest of is among their variants."""
    kept = load_split(EVALS / KEPT_FILE)
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    first = SplitFile(salt=kept.salt, items={i: s for i, s in kept.items.items() if i not in ADDED})
    assert len(first.items) == 64
    assert place_new(items, first) == kept.items
    added = [item for item in items if item.id in ADDED]
    assert len(added) == 6
    assert all(item.kind == "none" and item.needs_search and not item.expected for item in added)
    assert all(any(v.language == "msa" for v in item.variants) for item in added)


def test_an_item_added_later_is_placed_and_no_kept_item_moves() -> None:
    items = _set()
    kept = _kept(items)
    added = [_item(f"q{n:02}_added", kind="none", expected=[]) for n in range(10, 16)]
    # A kept item whose stratum changed keeps its side all the same.
    changed = items[1].model_copy(update={"kind": "small_talk", "needs_search": False})
    changed = changed.model_copy(update={"expected": ()})
    placed = place_new([*items[:1], changed, *items[2:], *added], kept)
    assert all(placed[item.id] == item.split for item in items)
    assert {i.id: placed[i.id] for i in added} == split_items(added, SALT)
    sides = [i.model_copy(update={"split": placed[i.id]}) for i in added]
    fix = "FIX: run `python -m ole5_voice.evals.split --keep --knowledge` and commit it"
    assert _problems([*items, *sides], kept=kept) == [
        f"{i.id}: not in knowledge/split.json; {fix}" for i in added
    ]
    assert _problems([*items, *sides], kept=_kept([*items, *sides])) == []


def test_an_item_off_its_kept_side_is_named() -> None:
    items = _set()
    kept = _kept(items)
    side = items[1].split
    wrong = "held-out" if side == "dev" else "dev"
    moved = [*items[:1], items[1].model_copy(update={"split": wrong}), *items[2:]]
    assert _problems(moved, kept=kept) == [
        f"q01_new: split {wrong}, the keep rule gives {side} (knowledge/split.json)"
    ]
    rule = split_items([_item("q03_late")], SALT)["q03_late"]
    other = "held-out" if rule == "dev" else "dev"
    late = _item("q03_late", split=other)
    fix = "FIX: run `python -m ole5_voice.evals.split --keep --knowledge` and commit it"
    assert _problems([*items, late], kept=kept) == [
        f"q03_late: split {other}, the keep rule gives {rule} (knowledge/split.json)",
        f"q03_late: not in knowledge/split.json; {fix}",
    ]


def test_the_committed_split_names_no_other_item_and_holds_the_sets_salt() -> None:
    items = _set()
    fix = "FIX: run `python -m ole5_voice.evals.split --keep --knowledge` and commit it"
    gone = _kept([*items, _item("q04_gone")])
    assert _problems(items, kept=gone) == [
        f"q04_gone: in knowledge/split.json but not an item; {fix}"
    ]
    salted = SplitFile(salt="another", items=_kept(items).items)
    assert _problems(items, kept=salted) == [
        f"knowledge/split.json: its salt is not the set's ({SALT})"
    ]
