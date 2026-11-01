"""The run history: `evals/history.jsonl`, and `poe eval-history`, which renders it.

Built by plan 002's Track F; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ole5_voice.evals.models import HistoryLine

_STUB = "history.py is built by plan 002's Track F"
_DESCRIPTION = "Render the golden set's run history into docs/generated/eval-history.md."


def append_line(line: HistoryLine, history: Path) -> None:
    """Add `line` to the end of `history`, with LF endings."""
    raise NotImplementedError(_STUB)


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe eval-history`: render the run history into docs/generated/eval-history.md."""
    parser = argparse.ArgumentParser(prog="poe eval-history", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
