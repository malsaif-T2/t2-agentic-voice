"""`poe eval-compare A B`: fixed, broken and net per variant, and the sign test by item.

Built by plan 002's Track F; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "compare.py is built by plan 002's Track F"
_DESCRIPTION = "Compare two runs: fixed, broken and net per variant, and the sign test by item."


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe eval-compare`: compare two runs variant by variant."""
    parser = argparse.ArgumentParser(prog="poe eval-compare", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
