"""The clause splitter (domain/text/clauses.py). Plan 003's Track A builds it and replaces this
file's stub test with its own."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.clauses import split_clauses


def test_the_clause_splitter_is_a_stub_until_track_a() -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        split_clauses("Made-up words, then more.", max_chars=200)
