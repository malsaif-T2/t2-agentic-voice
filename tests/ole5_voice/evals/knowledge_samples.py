"""A made-up knowledge set for the knowledge set's tests (test_knowledge_set.py,
test_knowledge_keep.py): one recorded request of a made-up golden set, and new items, each new
one split by the set's rule; and `check` run on it."""

from __future__ import annotations

from typing import Any

from ole5_voice.evals.knowledge_set import (
    SALT,
    Document,
    KnowledgeItem,
    Point,
    Points,
    check,
    count_knowledge,
)
from ole5_voice.evals.models import Item, SplitFile
from ole5_voice.evals.split import split_items

from tests.ole5_voice.evals import samples

# A made-up set: one recorded request of a made-up golden set, and new items.
POINTS = Points(
    documents=(Document(key="guide", name="A guide"),),
    points=(Point(id="guide-001", document="guide", chunk="chunk_001"),),
)


def golden_item(item_id: str, text: str) -> Item:
    """A golden item of `text`, with one variant."""
    item = samples.item(item_id, text=text)
    return item.model_copy(update={"variants": (samples.variant(f"{item_id}-1", text),)})


GOLDEN = (golden_item("b01_other", "stop now"), golden_item("n01_asked", "where is it"))
SPLIT = SplitFile(salt="s", items={"b01_other": "held-out", "n01_asked": "dev"})
RECORDED_WORDS = {"language": "english", "text": "where is it"}


def an_item(item_id: str, **changes: Any) -> KnowledgeItem:
    """A made-up answerable dev item, with `changes`."""
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


def recorded_item() -> KnowledgeItem:
    """The made-up golden set's recorded request, as a knowledge item."""
    return an_item("n01_asked", variants=[RECORDED_WORDS, {"language": "saudi", "text": "وينه"}])


def made_up_set(*extra: KnowledgeItem) -> list[KnowledgeItem]:
    """The recorded request, two new items and `extra`, each new one split by the rule."""
    new = [an_item("q01_new"), an_item("q02_none", kind="none", expected=[]), *extra]
    golden = {item.id for item in GOLDEN}
    sides = split_items([item for item in new if item.id not in golden], SALT)
    return [
        recorded_item(),
        *(i.model_copy(update={"split": sides.get(i.id, i.split)}) for i in new),
    ]


def problems_in(items: list[KnowledgeItem], **changes: Any) -> list[str]:
    """`check` on `items` against the made-up golden set, the floor left out, the registered
    counts the items' own unless `changes` gives others, and no committed split that keeps
    the sides unless `changes` gives one (`kept`)."""
    given: dict[str, Any] = {"points": POINTS, "strata": count_knowledge(items), "kept": None}
    given |= changes
    return check(
        items, given["points"], GOLDEN, SPLIT, given["strata"], floor=0, kept=given["kept"]
    )


def kept_as(items: list[KnowledgeItem]) -> SplitFile:
    """The committed split that keeps each of `items` on its side."""
    return SplitFile(salt=SALT, items={item.id: item.split for item in items})
