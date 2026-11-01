"""The import of the owner's new takes: their sidecars and reviews as items and manifests.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

_STUB = "import_recordings.py is built by plan 002's Track D"
_DESCRIPTION = "Import the recorder's takes as golden-set items and manifests (no audio)."


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m ole5_voice.evals.import_recordings`: write the new recordings' items and
    manifests from the recorder's files (no audio)."""
    parser = argparse.ArgumentParser(prog="import_recordings", description=_DESCRIPTION)
    parser.parse_args(argv)
    raise NotImplementedError(_STUB)


if __name__ == "__main__":
    sys.exit(main())
