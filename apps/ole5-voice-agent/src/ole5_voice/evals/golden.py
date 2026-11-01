"""`poe golden`: validate every item, and freeze the expected answers into one file.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "golden.py is built by plan 002's Track D"
_DESCRIPTION = "Validate the golden set's items and freeze their expected answers."


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe golden`: validate the golden set and freeze its expected answers."""
    parser = argparse.ArgumentParser(prog="poe golden", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
