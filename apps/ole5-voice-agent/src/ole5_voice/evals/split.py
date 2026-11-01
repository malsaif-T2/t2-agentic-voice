"""The held-out split: by item, stratified, from a salted order, committed and checked.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ole5_voice.evals.models import Item, Split

_STUB = "split.py is built by plan 002's Track D"
_DESCRIPTION = "Write the golden set's split, or check that the committed one is fresh."


def split_items(items: Sequence[Item], salt: str) -> dict[str, Split]:
    """Each item's split, by its ID, about 30% held out, stratified by language and kind."""
    raise NotImplementedError(_STUB)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.split`: write the split, or check the committed one
    (`--check`)."""
    parser = argparse.ArgumentParser(prog="split", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
