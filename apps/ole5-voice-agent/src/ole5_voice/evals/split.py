"""The held-out split: by item, stratified, from a salted order, committed and checked.

About 30% of the items are held out (evaluation.md, "Splits"), by item, so every variant of an
item lands on one side. Each stratum, an item's language and kind, holds out its share rounded
down; the items left over to reach 30% of the whole set, rounded to the nearest, go to the
strata with the largest remainders, ties broken by the salted order of their names. Inside a
stratum, the items are taken in the salted order of their IDs: the SHA-256 of the salt and the
ID. So the split depends only on the items' IDs and strata and the salt, which `split.json`
commits; `--check` fails when the committed split is not the one the items give.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

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
from ole5_voice.evals.models import Item, Split, SplitFile

log = get_logger(__name__)
_DESCRIPTION = "Write the golden set's split, or check that the committed one is fresh."
# The share held out, as tenths, so the arithmetic stays in integers.
HELD_OUT_TENTHS: Final = 3
# The salt of a split written for the first time; afterwards the committed one is kept.
DEFAULT_SALT: Final = "plan-002-2026-11-01"


def _order(salt: str, name: str) -> str:
    return hashlib.sha256(f"{salt}\n{name}".encode()).hexdigest()


def split_items(items: Sequence[Item], salt: str) -> dict[str, Split]:
    """Each item's split, by its ID, about 30% held out, stratified by language and kind."""
    if not salt:
        raise ValueError("a split needs a salt")
    strata: dict[str, list[Item]] = {}
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


def load_split(path: Path) -> SplitFile:
    """The committed `split.json`, checked as it is read: what the runner reads each item's
    split from."""
    return read_json(path, SplitFile)


def dump_split(split: SplitFile) -> str:
    """`split.json`'s text: its salt, then each item's split in the order of their IDs."""
    return split.model_dump_json(indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.split`: write the split, or check the committed one
    (`--check`)."""
    parser = argparse.ArgumentParser(prog="split", description=_DESCRIPTION)
    parser.add_argument("--evals", type=Path, default=EVALS, help="the golden set's folder")
    parser.add_argument("--salt", help="a new salt (by default the committed split's is kept)")
    parser.add_argument("--check", action="store_true", help="only check the committed split")
    args = parser.parse_args(argv)
    if args.check and args.salt:
        parser.error("--check checks the committed split, with its own salt")
    configure_logging(loggers=LOGGERS)
    path = args.evals / SPLIT_FILE
    try:
        items = load_items(args.evals / GOLDEN_DIR)
        committed = load_split(path) if path.is_file() or args.check else None
        salt = args.salt or (committed.salt if committed else DEFAULT_SALT)
        fresh = SplitFile(salt=salt, items=split_items(items, salt)) if items else None
    except (GoldenSetError, ValueError) as error:
        log.error("split_not_made", problem=str(error))
        return 1
    if fresh is None:
        log.error("split_not_made", problem="the golden set holds no item")
        return 1
    if args.check and committed is not None:
        named = fresh.items.keys() | committed.items.keys()
        changed = sorted(i for i in named if fresh.items.get(i) != committed.items.get(i))
        if changed:
            fix = "run `python -m ole5_voice.evals.split` and commit split.json"
            log.error("split_stale", items=changed, fix=fix)
            return 1
        log.info("split_fresh", items=len(fresh.items))
        return 0
    write_text(path, dump_split(fresh))
    held_out = sum(1 for s in fresh.items.values() if s == "held-out")
    log.info("split_written", items=len(fresh.items), held_out=held_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
