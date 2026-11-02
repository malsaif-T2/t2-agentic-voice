"""The clause splitter (the design's 13): the library's only one, so a reply is cut the same way
whether it is spoken or shown, and Pipecat's text-to-speech aggregation passes each clause
through whole (TOKEN), one request a clause. Built by plan 003's Track A; until then a stub.
Public through the `languages` facade.
"""

from __future__ import annotations

_STUB = "the clause splitter is built by plan 003's Track A"


def split_clauses(text: str, *, max_chars: int | None) -> tuple[str, ...]:
    """`text` cut into clauses at the Arabic comma and question mark, the full stop and English
    punctuation, each clause at most `max_chars` characters (the provider's `max_chars`; None for
    no limit), none cut inside a word, in order; no clause is empty, and a text with nothing to
    say gives none."""
    raise NotImplementedError(_STUB)
