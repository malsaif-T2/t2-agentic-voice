"""The held-out split: by item, stratified, from a salted order, committed and checked.

About 30% of the items are held out (evaluation.md, "Splits"), by item, so every variant of an
item lands on one side. Each stratum, an item's language and kind, holds out its share rounded
down; the items left over to reach 30% of the whole set, rounded to the nearest, go to the
strata with the largest remainders, ties broken by the salted order of their names. Inside a
stratum, the items are taken in the salted order of their IDs: the SHA-256 of the salt and the
ID. So the split depends only on the items' IDs and strata and the salt, which `split.json`
commits; `--check` fails when the committed split is not the one the items give.

Items added later (plan 005's recordings and imported calls) are placed with `--keep`
(`place_new`): every committed item keeps its side, whatever its stratum has become, so no item
moves between dev and held-out once a run has read it; the new items alone are split among
themselves by the same rule, with the committed salt; and an item no longer in the set leaves
the split. Once a split was written so, it is checked with `--check --keep`: every item has its
committed side, and no other is named.

The knowledge set (`knowledge_set.py`) keeps its own split the same way, with `--knowledge`:
`knowledge/split.json` froze the sides of its first 64 items (TD-114's keep path), so an item
added later is placed by `place_new` with that file's salt, and no item placed before moves. Its
split was never written whole, the recorded requests' sides being the golden set's, so it is
only kept (`--keep`) or checked (`--check --keep`).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Protocol

from t2_agentic_voice import configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals.items import (
    EVALS,
    GOLDEN_DIR,
    SPLIT_FILE,
    GoldenSetError,
    load_items,
    read_json,
    write_text,
)
from ole5_voice.evals.models import Split, SplitFile

log = get_logger(__name__)
_DESCRIPTION = "Write the golden set's split, or check that the committed one is fresh."
# The share held out, as tenths, so the arithmetic stays in integers.
HELD_OUT_TENTHS: Final = 3
# The salt of a split written for the first time; afterwards the committed one is kept.
DEFAULT_SALT: Final = "plan-002-2026-11-01"
# The command a FIX names once the split is committed: new items placed, none moved.
KEEP_COMMAND: Final = "python -m ole5_voice.evals.split --keep"
# The same for the knowledge set, whose split is only ever kept.
KNOWLEDGE_KEEP_COMMAND: Final = f"{KEEP_COMMAND} --knowledge"


class Stratified(Protocol):
    """What the split reads of an item: its ID and its strata. A golden item is one, and so is
    an item of the knowledge set (`knowledge_set.py`), which is split by the same rule."""

    @property
    def id(self) -> str: ...
    @property
    def language(self) -> str: ...
    @property
    def kind(self) -> str: ...


def _order(salt: str, name: str) -> str:
    return hashlib.sha256(f"{salt}\n{name}".encode()).hexdigest()


def split_items(items: Sequence[Stratified], salt: str) -> dict[str, Split]:
    """Each item's split, by its ID, about 30% held out, stratified by language and kind."""
    if not salt:
        raise ValueError("a split needs a salt")
    strata: dict[str, list[Stratified]] = {}
    for item in items:
        strata.setdefault(f"{item.language}/{item.kind}", []).append(item)
    target = (HELD_OUT_TENTHS * len(items) + 5) // 10
    held = {name: HELD_OUT_TENTHS * len(found) // 10 for name, found in strata.items()}
    remainders = sorted(
        strata,
        key=lambda name: (-(HELD_OUT_TENTHS * len(strata[name]) % 10), _order(salt, name)),
    )
    for name in remainders[: target - sum(held.values())]:
        held[name] += 1
    split: dict[str, Split] = {}
    for name, found in strata.items():
        ordered = sorted(found, key=lambda item: _order(salt, item.id))
        for n, item in enumerate(ordered):
            split[item.id] = "held-out" if n < held[name] else "dev"
    return dict(sorted(split.items()))


def place_new(items: Sequence[Stratified], committed: SplitFile) -> dict[str, Split]:
    """Each item's split, every committed item keeping its side and the others split among
    themselves (`split_items`, with the committed salt); an item no longer in the set left out."""
    kept = {item.id: committed.items[item.id] for item in items if item.id in committed.items}
    new = [item for item in items if item.id not in committed.items]
    return dict(sorted((kept | split_items(new, committed.salt)).items()))


def load_split(path: Path) -> SplitFile:
    """The committed `split.json`, checked as it is read: what the runner reads each item's
    split from."""
    return read_json(path, SplitFile)


def dump_split(split: SplitFile) -> str:
    """`split.json`'s text: its salt, then each item's split in the order of their IDs."""
    return split.model_dump_json(indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.split`: write the split, or check the committed one
    (`--check`); with `--keep`, every committed item keeping its side; with `--knowledge`, the
    knowledge set's, only kept."""
    parser = argparse.ArgumentParser(prog="split", description=_DESCRIPTION)
    parser.add_argument("--evals", type=Path, default=EVALS, help="the golden set's folder")
    parser.add_argument("--salt", help="a new salt (by default the committed split's is kept)")
    parser.add_argument("--check", action="store_true", help="only check the committed split")
    parser.add_argument("--keep", action="store_true", help="keep each committed item's side")
    parser.add_argument(
        "--knowledge", action="store_true", help="the knowledge set's split, which is only kept"
    )
    args = parser.parse_args(argv)
    if (args.check or args.keep) and args.salt:
        parser.error("--check and --keep take the committed split, with its own salt")
    if args.knowledge and not args.keep:
        parser.error("the knowledge set's split is only kept: --keep, or --check --keep")
    configure_logging(loggers=LOGGERS)
    try:
        path, items = _committed(args.evals, knowledge=args.knowledge)
        committed = load_split(path) if path.is_file() or args.check or args.keep else None
        salt = args.salt or (committed.salt if committed else DEFAULT_SALT)
        if not items:
            fresh = None
        elif args.keep and committed is not None:
            fresh = SplitFile(salt=salt, items=place_new(items, committed))
        else:
            fresh = SplitFile(salt=salt, items=split_items(items, salt))
    except (GoldenSetError, ValueError) as error:
        log.error("split_not_made", problem=str(error))
        return 1
    if fresh is None:
        log.error("split_not_made", problem="the set holds no item")
        return 1
    if args.check and committed is not None:
        named = fresh.items.keys() | committed.items.keys()
        changed = sorted(i for i in named if fresh.items.get(i) != committed.items.get(i))
        if changed:
            fix = (
                f"run `{KNOWLEDGE_KEEP_COMMAND}` and commit it"
                if args.knowledge
                else "run `python -m ole5_voice.evals.split` (with --keep once kept) and commit it"
            )
            log.error("split_stale", items=changed, fix=fix)
            return 1
        log.info("split_fresh", items=len(fresh.items))
        return 0
    write_text(path, dump_split(fresh))
    held_out = sum(1 for s in fresh.items.values() if s == "held-out")
    log.info("split_written", items=len(fresh.items), held_out=held_out)
    return 0


def _committed(evals: Path, *, knowledge: bool) -> tuple[Path, Sequence[Stratified]]:
    """The committed split's file and the items it splits: the golden set's, or with
    `knowledge` the knowledge set's, its split beside its items."""
    if not knowledge:
        return evals / SPLIT_FILE, load_items(evals / GOLDEN_DIR)
    # Imported here: the knowledge set's module imports this one.
    from ole5_voice.evals.knowledge_set import KNOWLEDGE_DIR, load_knowledge_items

    folder = evals / KNOWLEDGE_DIR
    return folder / SPLIT_FILE, load_knowledge_items(folder)


if __name__ == "__main__":
    sys.exit(main())
