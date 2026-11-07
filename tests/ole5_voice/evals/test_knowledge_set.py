"""The knowledge set (plan 006's registration, "Data"): the committed items break no rule; the
set is the one the registration describes; and each rule is shown failing on a made-up set
(knowledge_samples.py): the points, the recorded requests, each kind's rule, the variants and
key facts, the split, the floor and the registered counts. The split's keep path (TD-114):
test_knowledge_keep.py."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals.items import EVALS, GoldenSetError, read_toml
from ole5_voice.evals.knowledge_set import (
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
from ole5_voice.evals.models import SplitFile
from ole5_voice.evals.toml_write import dump_item
from pydantic import ValidationError

from tests.ole5_voice.evals.knowledge_samples import GOLDEN, POINTS, SPLIT
from tests.ole5_voice.evals.knowledge_samples import an_item as _item
from tests.ole5_voice.evals.knowledge_samples import kept_as as _kept
from tests.ole5_voice.evals.knowledge_samples import made_up_set as _set
from tests.ole5_voice.evals.knowledge_samples import problems_in as _problems
from tests.ole5_voice.evals.knowledge_samples import recorded_item as _recorded


def test_the_committed_knowledge_set_breaks_no_rule() -> None:
    assert problems(EVALS) == []


def test_the_set_is_the_one_the_registration_describes() -> None:
    items = load_knowledge_items(EVALS / KNOWLEDGE_DIR)
    recorded = [item for item in items if RECORDED.match(item.id)]
    new = [item for item in items if not RECORDED.match(item.id)]
    assert len(recorded) == 28 and len(new) == 42  # about 60, then 6 more `none` items (Q13)
    kinds = Counter(item.kind for item in new)
    assert kinds == {"answerable": 22, "none": 14, "small_talk": 3, "out_of_scope": 3}
    none = Counter(item.split for item in items if item.kind == "none")
    assert none == {"dev": 10, "held-out": 6}  # one miss on dev no longer fails the 90%
    dev = sum(1 for item in items if item.split == "dev")
    assert 0.6 < dev / len(items) < 0.7  # dev about two thirds
    variants = Counter(v.language for item in items for v in item.variants)
    assert variants.most_common(1)[0][0] == "saudi"  # Saudi the most, as the callers are
    points = read_toml(EVALS / KNOWLEDGE_DIR / POINTS_FILE, Points)
    assert (len(points.documents), len(points.points)) == (4, 126)  # the export's every chunk


def test_a_made_up_set_that_keeps_every_rule_has_no_problem() -> None:
    assert _problems(_set()) == []
    assert _problems(_set(), kept=_kept(_set())) == []


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
