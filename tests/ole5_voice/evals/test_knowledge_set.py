"""The knowledge set (plan 006's registration, "Data"): the committed items break no rule; the
set is the one the registration describes, its sides kept in `knowledge/split.json`; and each
rule is shown failing on a made-up set: the points, the recorded requests, each kind's rule, the
variants and key facts, the split and its keep path (TD-114), the floor and the registered
counts."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.items import EVALS, GoldenSetError, read_toml
from ole5_voice.evals.knowledge_set import (
    KEPT_FILE,
    KNOWLEDGE_DIR,
    POINTS_FILE,
    RECORDED,
    SALT,
    Document,
    KnowledgeItem,
    KnowledgeStrata,
    Point,
    Points,
    SplitCounts,
    check,
    count_knowledge,
    load_knowledge_items,
    problems,
)
from ole5_voice.evals.models import Item, SplitFile
from ole5_voice.evals.split import load_split, place_new, split_items
from ole5_voice.evals.toml_write import dump_item
from pydantic import ValidationError

from tests.ole5_voice.evals import samples


def test_the_committed_knowledge_set_breaks_no_rule() -> None:
    assert problems(EVALS) == []


def test_the_set_is_the_one_the_registration_describes() -> None:
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    recorded = [item for item in items if RECORDED.match(item.id)]
    new = [item for item in items if not RECORDED.match(item.id)]
    assert len(recorded) == 28 and len(new) == 36  # about 60 in all
    kinds = Counter(item.kind for item in new)
    assert kinds == {"answerable": 22, "none": 8, "small_talk": 3, "out_of_scope": 3}
    dev = sum(1 for item in items if item.split == "dev")
    assert 0.6 < dev / len(items) < 0.7  # dev about two thirds
    variants = Counter(v.language for item in items for v in item.variants)
    assert variants.most_common(1)[0][0] == "saudi"  # Saudi the most, as the callers are
    points = read_toml(EVALS / KNOWLEDGE_DIR / POINTS_FILE, Points)
    assert (len(points.documents), len(points.points)) == (4, 126)  # the export's every chunk


# A made-up set: one recorded request of a made-up golden set, and new items.
POINTS = Points(
    documents=(Document(key="guide", name="A guide"),),
    points=(Point(id="guide-001", document="guide", chunk="chunk_001"),),
)


def _golden(item_id: str, text: str) -> Item:
    item = samples.item(item_id, text=text)
    return item.model_copy(update={"variants": (samples.variant(f"{item_id}-1", text),)})


GOLDEN = (_golden("b01_other", "stop now"), _golden("n01_asked", "where is it"))
SPLIT = SplitFile(salt="s", items={"b01_other": "held-out", "n01_asked": "dev"})
RECORDED_WORDS = {"language": "english", "text": "where is it"}


def _item(item_id: str, **changes: Any) -> KnowledgeItem:
    base: dict[str, Any] = {
        "id": item_id,
        "split": "dev",
        "kind": "answerable",
        "needs_search": True,
        "variants": [
            {"language": "english", "text": f"{item_id} asked"},
            {"language": "saudi", "text": f"{item_id} وين"},
        ],
        "expected": ["guide-001"],
        "key_facts": ["says where", "says how"],
        "notes": "a made-up item",
    }
    return KnowledgeItem.model_validate(base | changes)


def _recorded() -> KnowledgeItem:
    return _item("n01_asked", variants=[RECORDED_WORDS, {"language": "saudi", "text": "وينه"}])


def _set(*extra: KnowledgeItem) -> list[KnowledgeItem]:
    """The recorded request, two new items and `extra`, each new one split by the rule."""
    new = [_item("q01_new"), _item("q02_none", kind="none", expected=[]), *extra]
    golden = {item.id for item in GOLDEN}
    sides = split_items([item for item in new if item.id not in golden], SALT)
    return [_recorded(), *(i.model_copy(update={"split": sides.get(i.id, i.split)}) for i in new)]


def _problems(items: list[KnowledgeItem], **changes: Any) -> list[str]:
    """`check` on `items` against the made-up golden set, the floor left out, the registered
    counts the items' own unless `changes` gives others, and no committed split that keeps
    the sides unless `changes` gives one (`kept`)."""
    given: dict[str, Any] = {"points": POINTS, "strata": count_knowledge(items), "kept": None}
    given |= changes
    return check(
        items, given["points"], GOLDEN, SPLIT, given["strata"], floor=0, kept=given["kept"]
    )


def test_a_made_up_set_that_keeps_every_rule_has_no_problem() -> None:
    assert _problems(_set()) == []
    assert _problems(_set(), kept=_kept(_set())) == []


def test_the_committed_split_keeps_every_items_side() -> None:
    """`knowledge/split.json` names every item with the side its file gives, under the set's
    salt; the 64 items drafted first are all in it (TD-114's keep path)."""
    kept = load_split(EVALS / KEPT_FILE)
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    assert kept.salt == SALT
    assert kept.items == {item.id: item.split for item in items}


def _kept(items: list[KnowledgeItem]) -> SplitFile:
    """The committed split that keeps each of `items` on its side."""
    return SplitFile(salt=SALT, items={item.id: item.split for item in items})


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


def test_each_points_rule_is_checked() -> None:
    broken = Points(
        documents=(Document(key="guide", name="A"), Document(key="guide", name="B")),
        points=(
            Point(id="guide-001", document="guide", chunk="chunk_001"),
            Point(id="guide-001", document="guide", chunk="chunk_001"),
            Point(id="other-002", document="other", chunk="chunk_002"),
            Point(id="guide-009", document="guide", chunk="chunk_003"),
        ),
    )
    assert _problems(_set(), points=broken) == [
        "points.toml: the document 'guide' twice",
        "points.toml: the point 'guide-001' twice",
        "points.toml: other-002 names no listed document",
        "points.toml: guide-009 is not its document's key and chunk number",
    ]
    lonely = Points(
        documents=(*POINTS.documents, Document(key="empty", name="C")), points=POINTS.points
    )
    assert _problems(_set(), points=lonely) == ["points.toml: the document 'empty' has no point"]


def test_the_recorded_requests_keep_their_ids_splits_and_words() -> None:
    items = _set()
    assert _problems(items[1:]) == ["n01_asked: a recorded request with no item"]
    moved = [items[0].model_copy(update={"split": "held-out"}), *items[1:]]
    assert _problems(moved) == ["n01_asked: its split is not split.json's"]
    reworded = [_item("n01_asked"), *items[1:]]
    assert _problems(reworded) == [
        "n01_asked: its first variant is not the recorded words and language"
    ]
    found = _problems(_set(_item("b01_other"), _item("n05_unknown")))
    assert found == [
        "b01_other: a golden item's ID but not a recorded request's",
        "n05_unknown: named as a recorded request the golden set does not hold",
    ]


def test_each_kinds_rule_is_checked() -> None:
    found = _problems(
        _set(
            _item("q03_no_points", expected=[]),
            _item("q04_talk", kind="small_talk"),
            _item("q05_none", kind="none", needs_search=False, expected=[]),
            _item("q06_unknown", expected=["guide-002", "guide-001", "guide-001"]),
        )
    )
    assert found == [
        "q03_no_points: expected points exactly when answerable",
        "q04_talk: expected points exactly when answerable",
        "q04_talk: needs a search exactly when answerable or none",
        "q05_none: needs a search exactly when answerable or none",
        "q06_unknown: expects 'guide-002', which points.toml does not hold",
        "q06_unknown: expects a point twice",
    ]


def test_the_variants_and_key_facts_are_each_given_once() -> None:
    same = [
        {"language": "english", "text": "Same words"},
        {"language": "msa", "text": "same  words"},
    ]
    copied = [
        {"language": "english", "text": "q01_new asked"},
        {"language": "msa", "text": "مختلف"},
    ]
    found = _problems(
        _set(
            _item("q07_twice", variants=same, key_facts=["says where", "Says  where"]),
            _item("q08_copy", variants=copied),
        )
    )
    assert found == [
        "q07_twice: holds a variant twice",
        "q07_twice: holds a key fact twice",
        "a variant in q01_new, q08_copy",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"variants": [{"language": "english", "text": "alone"}]},
        {"variants": [{"language": "english", "text": f"v{n}"} for n in range(5)]},
        {"key_facts": ["one"]},
        {"key_facts": ["a", "b", "c", "d", "e"]},
        {"variants": [{"language": "none", "text": "x"}, {"language": "english", "text": "y"}]},
        {"notes": " spaced"},
        {"notes": ""},
        {"key_facts": ["two\nlines", "b"]},
        {"kind": "request"},
        {"expected": ["guide-1"]},
        {"extra": "a field no item has"},
    ],
)
def test_an_item_out_of_its_shape_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _item("q09_bad", **changes)


def test_the_new_items_are_split_by_the_rule() -> None:
    items = _set()
    side = items[1].split
    wrong = "held-out" if side == "dev" else "dev"
    moved = [*items[:1], items[1].model_copy(update={"split": wrong}), *items[2:]]
    assert _problems(moved) == [f"q01_new: split {wrong}, the rule gives {side} (salt {SALT})"]


def test_each_language_needs_its_floor_of_answerable_dev_items() -> None:
    items = _set()
    found = check(items, POINTS, GOLDEN, SPLIT, count_knowledge(items))
    dev = sum(1 for i in items if i.split == "dev" and i.kind == "answerable")
    assert found == [
        f"{dev} answerable dev items with a variant in saudi, under 6",
        "0 answerable dev items with a variant in msa, under 6",
        f"{dev} answerable dev items with a variant in english, under 6",
        "0 answerable dev items with a variant in mixed, under 6",
    ]
    assert check(items, POINTS, GOLDEN, SPLIT, count_knowledge(items), floor=dev) == [
        "0 answerable dev items with a variant in msa, under " + str(dev),
        "0 answerable dev items with a variant in mixed, under " + str(dev),
    ]


def test_the_registered_counts_must_match() -> None:
    items = _set()
    counted = count_knowledge(items)
    dev = [i for i in items if i.split == "dev"]
    assert counted.split["dev"].items == len(dev)
    assert counted.split["dev"].variants == 2 * len(dev)
    assert counted.split["dev"].language == dict(Counter(i.language for i in dev))
    other = KnowledgeStrata(split={**counted.split, "dev": SplitCounts(items=0, variants=0)})
    (found,) = _problems(items, strata=other)
    assert found.startswith("knowledge/strata.toml registers other counts than the items hold")


def _dump(item: KnowledgeItem) -> str:
    """An item's TOML, its scalars and lists written as JSON, which TOML reads alike."""
    data = item.model_dump(exclude={"variants"})
    lines = [f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()]
    for variant in item.variants:
        lines += ["[[variants]]"]
        lines += [
            f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in variant.model_dump().items()
        ]
    return "\n".join(lines) + "\n"


def _strata(strata: KnowledgeStrata) -> str:
    lines = []
    for split, counts in strata.split.items():
        lines += [f"[split.{split}]", f"items = {counts.items}", f"variants = {counts.variants}"]
        for table in ("kind", "language", "variant_language", "answerable_language"):
            lines += [f"[split.{split}.{table}]"]
            lines += [f"{key} = {n}" for key, n in getattr(counts, table).items()]
    return "\n".join(lines) + "\n"


def test_the_files_are_read_strictly_and_checked_whole(tmp_path: Path) -> None:
    evals = tmp_path / "evals"
    folder = evals / KNOWLEDGE_DIR
    with pytest.raises(GoldenSetError, match="no such folder"):
        load_knowledge_items(folder)
    folder.mkdir(parents=True)
    (evals / "golden").mkdir()
    for golden in GOLDEN:
        (evals / "golden" / f"{golden.id}.toml").write_text(dump_item(golden), encoding="utf-8")
    (evals / "split.json").write_text(SPLIT.model_dump_json(), encoding="utf-8")
    items = _set()
    for item in items:
        (folder / f"{item.id}.toml").write_text(_dump(item), encoding="utf-8")
    points = '[[documents]]\nkey = "guide"\nname = "A guide"\n\n'
    points += '[[points]]\nid = "guide-001"\ndocument = "guide"\nchunk = "chunk_001"\n'
    (folder / POINTS_FILE).write_text(points, encoding="utf-8")
    (folder / "strata.toml").write_text(_strata(count_knowledge(items)), encoding="utf-8")
    with pytest.raises(GoldenSetError, match=re.escape("split.json")):
        problems(evals)  # no committed split that keeps the sides
    kept = SplitFile(salt=SALT, items={item.id: "dev" for item in items})
    (folder / "split.json").write_text(kept.model_dump_json(), encoding="utf-8")
    assert load_knowledge_items(folder) == tuple(sorted(items, key=lambda item: item.id))
    counted = count_knowledge(items)
    assert problems(evals) == check(items, POINTS, GOLDEN, SPLIT, counted, kept=kept) != []
    (folder / "q99_elsewhere.toml").write_text(_dump(items[1]), encoding="utf-8")
    with pytest.raises(
        GoldenSetError, match=re.escape("q99_elsewhere.toml: holds the item 'q01_new'")
    ):
        load_knowledge_items(folder)


def test_an_items_language_is_its_first_variants() -> None:
    assert _item("q10_language").language == "english"
    assert _recorded().language == "english"
