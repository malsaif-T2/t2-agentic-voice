"""`poe eval`: run an answerer over the golden set, as evaluation.md's "Running" says.

Built by plan 002's Track E; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "run.py is built by plan 002's Track E"
_DESCRIPTION = "Run an answerer over the golden set, writing its results and scorecard into --out."


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe eval`: run an answerer over the golden set into a new folder."""
    parser = argparse.ArgumentParser(prog="poe eval", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
