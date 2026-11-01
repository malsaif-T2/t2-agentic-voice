"""The matcher: whether an output says a reference, under Ole5's spelling guide.

Built by plan 002's Track D; until then a stub.
"""

from __future__ import annotations

from pathlib import Path

from ole5_voice.evals.models import Matcher

_STUB = "matcher.py is built by plan 002's Track D"


def load_matcher(spelling: Path) -> Matcher:
    """The matcher of the spelling guide in `spelling` (`evals/spelling.toml`)."""
    raise NotImplementedError(_STUB)
