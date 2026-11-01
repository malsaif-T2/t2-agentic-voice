"""The redaction hook: what a team does not want exported is replaced before a span leaves.

The patterns are the team's (`tracing.redact`), applied by the tracing helpers to every text
attribute of every span they make (the design's 10.1). Every match of every pattern is found in
the original text, and each stretch any of them matched becomes one replacement, so patterns
that overlap leave no piece of a match behind, and a replacement is never matched again. Public
through the `tracing` facade (D-021).
"""

from __future__ import annotations

import re
from collections.abc import Sequence


class Redactor:
    """Replaces every match of a team's regular expressions in a text. Its repr shows no
    pattern, since a team may write a value it wants kept out as a pattern."""

    def __init__(self, patterns: Sequence[str], *, replacement: str = "[redacted]") -> None:
        if isinstance(patterns, str):
            raise TypeError("patterns is a sequence of regular expressions, not one string")
        self._patterns = tuple(re.compile(pattern) for pattern in patterns)
        self._replacement = replacement

    def __call__(self, text: str) -> str:
        """`text` with every match of the patterns replaced by the replacement."""
        found = sorted(
            match.span()
            for pattern in self._patterns
            for match in pattern.finditer(text)
            if match.end() > match.start()  # an empty match hides nothing
        )
        parts: list[str] = []
        done = 0
        for start, end in found:
            if end <= done:  # inside a stretch already replaced
                continue
            if start >= done:
                parts.append(text[done:start])
                parts.append(self._replacement)
            done = end
        parts.append(text[done:])
        return "".join(parts)
