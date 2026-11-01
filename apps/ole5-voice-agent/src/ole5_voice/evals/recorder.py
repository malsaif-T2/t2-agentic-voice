"""`poe record`: the page the owner records and reviews the golden set's takes with.

Built by plan 002's Track G; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "recorder.py is built by plan 002's Track G"
_DESCRIPTION = "Serve the page to record and review the golden set's new takes, on 127.0.0.1."


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe record`: serve the recorder's page on 127.0.0.1."""
    parser = argparse.ArgumentParser(prog="poe record", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
