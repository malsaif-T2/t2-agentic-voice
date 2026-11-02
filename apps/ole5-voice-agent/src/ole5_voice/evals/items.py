"""The golden set's items: read from their TOML files under `evals/golden/`, with the other
files of `evals/` they are checked against.

`evals/` holds, besides `golden/` (one item a file, named by its ID): `manifests/` (one
`Manifest` a file: `talkover.json`, and `<root>-<session>.json` for each recording session),
`frozen.json` (the expected answers `poe golden` freezes), `split.json`, `strata.toml` (the
registered counts), `terms.toml` (the product terms), `script.toml` (the new recordings'
script), `spelling.toml` (the spelling guide), `allowed_in_source.toml` and `history.jsonl` (the
run history, `history.py`). Every file is
parsed strictly as it is read, and a file that cannot be read is a `GoldenSetError` naming it,
never echoing what it holds.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from ole5_voice.evals.files import read_model
from ole5_voice.evals.models import (
    Confirmation,
    Item,
    Manifest,
    Model,
    ReferenceSource,
    Variant,
)
from ole5_voice.evals.takes import Review, Script

# The app's golden-set data, beside its `src/`.
EVALS: Final = Path(__file__).resolve().parents[3] / "evals"
GOLDEN_DIR: Final = "golden"
MANIFESTS_DIR: Final = "manifests"
FROZEN_FILE: Final = "frozen.json"
SPLIT_FILE: Final = "split.json"
STRATA_FILE: Final = "strata.toml"
TERMS_FILE: Final = "terms.toml"
SCRIPT_FILE: Final = "script.toml"
SPELLING_FILE: Final = "spelling.toml"
HISTORY_FILE: Final = "history.jsonl"  # a run's line is also copied beside its scorecard


class GoldenSetError(ValueError):
    """A golden-set file that cannot be read as written, or a set that breaks a rule."""


def read_toml[M: BaseModel](path: Path, model: type[M]) -> M:
    """`path`'s TOML as `model`; GoldenSetError naming the file, and the fields only, when it
    cannot be read as UTF-8 text, is not TOML, or does not fit (`files.read_model`)."""
    return read_model(
        path, model, lambda problem: GoldenSetError(f"{path.name}: {problem}"), toml=True
    )


def read_json[M: BaseModel](path: Path, model: type[M]) -> M:
    """`path`'s JSON as `model`, failing as `read_toml` does."""
    return read_model(path, model, lambda problem: GoldenSetError(f"{path.name}: {problem}"))


def write_text(path: Path, text: str) -> None:
    """`text` as UTF-8 with LF endings, the folders above it made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def dump_manifest(manifest: Manifest) -> str:
    """A manifest's committed text, whichever import writes it: JSON, its non-ASCII text as
    written, indented by two, with an LF at the end."""
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def holds_term(text: str, term: str) -> bool:
    """Whether `text` holds the product term `term` as a whole word, as the product writes it:
    how the talk-over import picks an item's terms, and `poe golden` checks them."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def references(item: Item, variant: Variant) -> tuple[str, ...]:
    """What counts as right for `variant`: its reference, then its item's alternatives (the
    expected answers `frozen.json` lists, and a run's verdict takes)."""
    return (variant.reference, *item.alternatives)


def load_items(folder: Path) -> tuple[Item, ...]:
    """Every item under `folder`, one TOML file each, in the order of their IDs. Each file is
    named by its item's ID, and no two variants share an ID."""
    if not folder.is_dir():
        raise GoldenSetError(f"{folder.name}: no such folder of items")
    items = []
    for path in sorted(folder.glob("*.toml")):
        item = read_toml(path, Item)
        if item.id != path.stem:
            raise GoldenSetError(f"{path.name}: holds the item '{item.id}', not '{path.stem}'")
        items.append(item)
    twice = [v for v, n in Counter(v.id for i in items for v in i.variants).items() if n > 1]
    if twice:
        raise GoldenSetError(f"variants with the same ID in two places: {', '.join(twice)}")
    return tuple(sorted(items, key=lambda item: item.id))


def load_manifests(folder: Path) -> tuple[Manifest, ...]:
    """Every manifest under `folder`, in the order of their file names; no file named twice
    below one root."""
    manifests = tuple(read_json(path, Manifest) for path in sorted(folder.glob("*.json")))
    named = Counter((m.root, f.path) for m in manifests for f in m.files)
    twice = sorted(f"{root}:{path}" for (root, path), n in named.items() if n > 1)
    if twice:
        raise GoldenSetError(f"files in two manifests: {', '.join(twice)}")
    return manifests


class Terms(Model):
    """`terms.toml`: the product terms term recall is scored on, as the product writes them."""

    terms: tuple[str, ...] = Field(min_length=1)


def load_terms(path: Path) -> tuple[str, ...]:
    terms = read_toml(path, Terms).terms
    if len(set(terms)) != len(terms) or not all(t.strip() == t and t for t in terms):
        raise GoldenSetError(f"{path.name}: each term once, with no space around it")
    return terms


def unchecked(variant: Variant) -> str | None:
    """Why `variant` is not yet checked, or None when it is: its reference and an independent
    check agree once the owner has listened and confirmed it (Q9). A typed reference's first
    act is the typing; its confirmation, in a later review pass, is its second."""
    if variant.confirmations:
        return None
    if variant.reference_source == "typed":
        return "typed by the owner, waiting on its second confirmation in a later review pass"
    return "not yet confirmed by the owner's listen"


def reviewed(
    reference: str, source: ReferenceSource, reviews: Sequence[Review]
) -> tuple[str, ReferenceSource, tuple[Confirmation, ...]]:
    """A variant's reference, its source and its confirmations after the owner's reviews, in
    the order of their passes. A typed review makes its text the reference and drops every
    earlier confirmation, which confirmed another text; only a confirmation in a later pass
    counts for it, so a reference and its check are never made in one act."""
    passes = [r.review_pass for r in reviews]
    if len(set(passes)) != len(passes):
        raise GoldenSetError("a take has one review in each pass")
    confirmations: list[Confirmation] = []
    for review in sorted(reviews, key=lambda r: r.review_pass):
        if review.verdict == "typed":
            text = " ".join(review.text.split())
            if not text:
                raise GoldenSetError(f"the review {review.review_pass} of {review.take} is empty")
            reference, source, confirmations = text, "typed", []
        else:
            confirmations.append(Confirmation(at=review.at, review_pass=review.review_pass))
    return reference, source, tuple(confirmations)


class Counts(Model):
    """How many items, variants or script lines a stratum holds, by each of its labels."""

    total: int = Field(ge=0)
    source: dict[str, int] = Field(default_factory=dict)
    language: dict[str, int] = Field(default_factory=dict)
    kind: dict[str, int] = Field(default_factory=dict)
    device: dict[str, int] = Field(default_factory=dict)
    tag: dict[str, int] = Field(default_factory=dict)


class Strata(Model):
    """`strata.toml`: the registered counts of the items, their variants and the script's lines,
    which the committed set must hold (evaluation.md, "Writing items": strata in fixed
    proportions, which a test enforces)."""

    items: Counts
    variants: Counts
    script: Counts


def count_strata(items: Sequence[Item], script: Script) -> Strata:
    """The strata the items and the script hold, counted."""
    variants = [(item, variant) for item in items for variant in item.variants]
    return Strata(
        items=Counts(
            total=len(items),
            source=_count(i.source for i in items),
            language=_count(i.language for i in items),
            kind=_count(i.kind for i in items),
        ),
        variants=Counts(
            total=len(variants),
            language=_count(i.language for i, _ in variants),
            kind=_count(i.kind for i, _ in variants),
            device=_count(v.device for _, v in variants),
            tag=_count(tag for _, v in variants for tag in v.tags),
        ),
        script=Counts(
            total=len(script.lines),
            language=_count(line.language for line in script.lines),
            kind=_count(line.kind for line in script.lines),
        ),
    )


def _count(labels: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(labels).items()))
