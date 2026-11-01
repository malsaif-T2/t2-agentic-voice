"""The import of the prototype's 124 talk-over segments as items, read in place (D-010).

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "import_talkover.py is built by plan 002's Track D"
_DESCRIPTION = (
    "Import the talk-over segments as golden-set items (writes only into this repository)."
)


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.import_talkover`: write the talk-over items and manifest from
    the lab's refs.json and takes.json."""
    parser = argparse.ArgumentParser(prog="import_talkover", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
