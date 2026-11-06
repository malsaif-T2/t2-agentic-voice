"""The knowledge set: the requests the talker's answers are measured on (plan 006's registration,
"Data"), one TOML file an item under `evals/knowledge/`, beside `points.toml` (every chunk of
Ole5's knowledge base, by its document and chunk, with no text) and `strata.toml` (the counts
the set must hold).

An item has its split, its kind (`answerable`, `none` for what the knowledge base does not hold,
`small_talk`, `out_of_scope`), whether it needs a search, two to four variants (a caller's words
and their language), the points that answer it (an `answerable` item's only), two to four key
facts an answer must hold (for the other kinds, what the agent does instead) and notes on what
it tests. The golden set's recorded requests `n01` to `n28` are items here under their own IDs
and splits, their first variant the words recorded, so their recordings serve the time to first
audio; every other item is split by the golden set's rule (`split.split_items`) with this set's
salt. `problems` lists each rule the committed set breaks, and
tests/ole5_voice/evals/test_knowledge_set.py holds it to none inside `poe check`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Annotated, Final, Literal, get_args

from pydantic import AfterValidator, Field, StringConstraints

from ole5_voice.evals.items import (
    GOLDEN_DIR,
    SPLIT_FILE,
    STRATA_FILE,
    GoldenSetError,
    load_items,
    read_toml,
)
from ole5_voice.evals.models import Item, Model, Name, Split, SplitFile
from ole5_voice.evals.split import load_split, split_items

KNOWLEDGE_DIR: Final = "knowledge"
POINTS_FILE: Final = "points.toml"
# The salt of the split of the items the golden set does not hold (`split.split_items`).
SALT: Final = "plan-006-2026-11-06"
# The fewest answerable dev items with a variant in each language: the smallest change one run
# can detect by the sign test on items (D-024).
DEV_FLOOR: Final = 6
# The golden set's recorded requests the knowledge set holds, by the start of their IDs.
RECORDED: Final = re.compile(r"n(0[1-9]|1[0-9]|2[0-8])_")

KnowledgeKind = Literal["answerable", "none", "small_talk", "out_of_scope"]
# A variant's language: `mixed` is Arabic with English product terms.
SpokenLanguage = Literal["saudi", "msa", "english", "mixed"]
LANGUAGES: Final = get_args(SpokenLanguage)
SPLITS: Final[tuple[Split, ...]] = ("dev", "held-out")
# The kinds whose answer needs a search: an answer, or a search that finds nothing to answer.
SEARCHED: Final = frozenset({"answerable", "none"})


def _one_line(value: str) -> str:
    if not value or value != value.strip() or "\n" in value:
        raise ValueError("one line of text, with no space around it")
    return value


Text = Annotated[str, AfterValidator(_one_line)]
DocumentKey = Annotated[str, StringConstraints(pattern=r"^[a-z]+$")]
# A point's ID: its document's key and its chunk's number, such as `rules-006`.
PointId = Annotated[str, StringConstraints(pattern=r"^[a-z]+-[0-9]{3}$")]


class KnowledgeVariant(Model):
    """One way a caller asks: the words, as said, and their language."""

    language: SpokenLanguage
    text: Text


class KnowledgeItem(Model):
    """One request the talker is measured on (plan 006, "Data")."""

    id: Name
    split: Split
    kind: KnowledgeKind
    needs_search: bool
    variants: tuple[KnowledgeVariant, ...] = Field(min_length=2, max_length=4)
    expected: tuple[PointId, ...] = ()  # the points that answer it
    key_facts: tuple[Text, ...] = Field(min_length=2, max_length=4)
    notes: Text  # what it tests, never what the data holds

    @property
    def language(self) -> SpokenLanguage:
        """The item's language, which its split is stratified by: its first variant's."""
        return self.variants[0].language


class Document(Model):
    """One document of the knowledge base: the key its points' IDs start with, and its name."""

    key: DocumentKey
    name: Text


class Point(Model):
    """One chunk of a document, as the export names it: no text."""

    id: PointId
    document: DocumentKey
    chunk: Annotated[str, StringConstraints(pattern=r"^chunk_[0-9]{3}$")]
    page: int | None = Field(default=None, ge=1)  # none in an export of Markdown documents


class Points(Model):
    """`points.toml`: the knowledge base's documents and every chunk of them."""

    documents: tuple[Document, ...] = Field(min_length=1)
    points: tuple[Point, ...] = Field(min_length=1)


class SplitCounts(Model):
    """How many items and variants one split holds, by kind and language."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    kind: dict[str, int] = Field(default_factory=dict)
    language: dict[str, int] = Field(default_factory=dict)  # items, by their first variant's
    variant_language: dict[str, int] = Field(default_factory=dict)
    # Answerable items with a variant in each language.
    answerable_language: dict[str, int] = Field(default_factory=dict)


class KnowledgeStrata(Model):
    """`knowledge/strata.toml`: the registered counts of each split."""

    split: dict[Split, SplitCounts]


def load_knowledge_items(folder: Path) -> tuple[KnowledgeItem, ...]:
    """Every item under `folder`, one TOML file each named by its ID, in the order of their IDs;
    `points.toml` and `strata.toml` are not items."""
    if not folder.is_dir():
        raise GoldenSetError(f"{folder.name}: no such folder of items")
    items = []
    for path in sorted(folder.glob("*.toml")):
        if path.name in (POINTS_FILE, STRATA_FILE):
            continue
        item = read_toml(path, KnowledgeItem)
        if item.id != path.stem:
            raise GoldenSetError(f"{path.name}: holds the item '{item.id}', not '{path.stem}'")
        items.append(item)
    return tuple(sorted(items, key=lambda item: item.id))


def count_knowledge(items: Sequence[KnowledgeItem]) -> KnowledgeStrata:
    """The counts the items hold, by split."""
    return KnowledgeStrata(split={s: _counts([i for i in items if i.split == s]) for s in SPLITS})


def _counts(items: Sequence[KnowledgeItem]) -> SplitCounts:
    answerable = [item for item in items if item.kind == "answerable"]
    return SplitCounts(
        items=len(items),
        variants=sum(len(item.variants) for item in items),
        kind=_count(item.kind for item in items),
        language=_count(item.language for item in items),
        variant_language=_count(v.language for item in items for v in item.variants),
        answerable_language=_count(
            language for item in answerable for language in {v.language for v in item.variants}
        ),
    )


def _count(labels: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(labels).items()))


def problems(evals: Path) -> list[str]:
    """Every rule the knowledge set under `evals` breaks, against the golden set beside it; a
    file that cannot be read is a GoldenSetError naming it."""
    folder = evals / KNOWLEDGE_DIR
    return check(
        load_knowledge_items(folder),
        read_toml(folder / POINTS_FILE, Points),
        load_items(evals / GOLDEN_DIR),
        load_split(evals / SPLIT_FILE),
        read_toml(folder / STRATA_FILE, KnowledgeStrata),
    )


def check(
    items: Sequence[KnowledgeItem],
    points: Points,
    golden: Sequence[Item],
    split: SplitFile,
    strata: KnowledgeStrata,
    *,
    floor: int = DEV_FLOOR,
) -> list[str]:
    """Every rule the items break: the points, the recorded requests, each item's kind, the
    split, the floor (the fewest answerable dev items with a variant in each language) and the
    registered counts."""
    found = _point_problems(points)
    found += _recorded_problems(items, golden, split)
    known = {point.id for point in points.points}
    for item in items:
        found += [f"{item.id}: {problem}" for problem in _item_problems(item, known)]
    found += _twice(items)
    found += _split_problems(items, golden)
    found += _floor_problems(items, floor)
    if count_knowledge(items) != strata:
        found.append(
            f"{KNOWLEDGE_DIR}/{STRATA_FILE} registers other counts than the items hold: "
            f"they hold {count_knowledge(items).model_dump_json()}"
        )
    return found


def _point_problems(points: Points) -> list[str]:
    keys = [document.key for document in points.documents]
    found = [f"{POINTS_FILE}: the document '{key}' twice" for key in _repeated(keys)]
    found += [
        f"{POINTS_FILE}: the point '{i}' twice" for i in _repeated(p.id for p in points.points)
    ]
    for point in points.points:
        if point.document not in keys:
            found.append(f"{POINTS_FILE}: {point.id} names no listed document")
        if point.id != f"{point.document}-{point.chunk.removeprefix('chunk_')}":
            found.append(f"{POINTS_FILE}: {point.id} is not its document's key and chunk number")
    named = {point.document for point in points.points}
    found += [f"{POINTS_FILE}: the document '{k}' has no point" for k in keys if k not in named]
    return found


def _recorded_problems(
    items: Sequence[KnowledgeItem], golden: Sequence[Item], split: SplitFile
) -> list[str]:
    """Each recorded request is an item, with its split and its recorded words first; no other
    item takes a golden item's ID."""
    by_id = {item.id: item for item in items}
    recorded = [item for item in golden if RECORDED.match(item.id)]
    found = []
    for request in recorded:
        item = by_id.get(request.id)
        if item is None:
            found.append(f"{request.id}: a recorded request with no item")
            continue
        if item.split != split.items.get(request.id):
            found.append(f"{item.id}: its split is not {SPLIT_FILE}'s")
        first = item.variants[0]
        if (first.text, first.language) != (request.text, request.language):
            found.append(f"{item.id}: its first variant is not the recorded words and language")
    names = {item.id for item in golden} - {item.id for item in recorded}
    found += [f"{i}: a golden item's ID but not a recorded request's" for i in by_id if i in names]
    found += [
        f"{i}: named as a recorded request the golden set does not hold"
        for i in by_id
        if RECORDED.match(i) and i not in {item.id for item in recorded}
    ]
    return found


def _item_problems(item: KnowledgeItem, known: set[str]) -> list[str]:
    answerable = item.kind == "answerable"
    found = []
    if answerable != bool(item.expected):
        found.append("expected points exactly when answerable")
    if item.needs_search != (item.kind in SEARCHED):
        found.append("needs a search exactly when answerable or none")
    found += [
        f"expects '{point}', which {POINTS_FILE} does not hold"
        for point in item.expected
        if point not in known
    ]
    if _repeated(item.expected):
        found.append("expects a point twice")
    if _repeated(_folded(v.text) for v in item.variants):
        found.append("holds a variant twice")
    if _repeated(_folded(fact) for fact in item.key_facts):
        found.append("holds a key fact twice")
    return found


def _twice(items: Sequence[KnowledgeItem]) -> list[str]:
    """No variant's words in two items, so an item, not a variant, is the unit."""
    owners: dict[str, set[str]] = {}
    for item in items:
        for variant in item.variants:
            owners.setdefault(_folded(variant.text), set()).add(item.id)
    return [f"a variant in {', '.join(sorted(o))}" for o in owners.values() if len(o) > 1]


def _split_problems(items: Sequence[KnowledgeItem], golden: Sequence[Item]) -> list[str]:
    """The items the golden set does not hold are split by its rule, with this set's salt."""
    names = {item.id for item in golden}
    new = [item for item in items if item.id not in names]
    wanted = split_items(new, SALT) if new else {}
    return [
        f"{item.id}: split {item.split}, the rule gives {wanted[item.id]} (salt {SALT})"
        for item in new
        if item.split != wanted[item.id]
    ]


def _floor_problems(items: Sequence[KnowledgeItem], floor: int) -> list[str]:
    held = count_knowledge(items).split["dev"].answerable_language
    return [
        f"{held.get(language, 0)} answerable dev items with a variant in {language}, under {floor}"
        for language in LANGUAGES
        if held.get(language, 0) < floor
    ]


def _folded(text: str) -> str:
    return " ".join(text.casefold().split())


def _repeated(values: Iterable[str]) -> list[str]:
    return sorted(value for value, n in Counter(values).items() if n > 1)
