"""The redaction hook: what a team does not want exported is replaced before a span leaves.

Built by plan 002's Track C; until then a stub. The patterns are the team's
(`tracing.redact`), applied to every text attribute of every span (the design's 10.1). Public
through the `tracing` facade (D-021).
"""

from __future__ import annotations

from collections.abc import Sequence

_STUB = "the Redactor is built by plan 002's Track C"


class Redactor:
    """Replaces every match of a team's regular expressions in a text."""

    def __init__(self, patterns: Sequence[str], *, replacement: str = "[redacted]") -> None:
        raise NotImplementedError(_STUB)

    def __call__(self, text: str) -> str:
        """`text` with every match of the patterns replaced by the replacement."""
        raise NotImplementedError(_STUB)
