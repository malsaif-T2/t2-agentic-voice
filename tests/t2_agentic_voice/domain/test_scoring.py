"""term_recall, id_recall and silence_output. Plan 002's Track A builds them and replaces this
file's stub tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from t2_agentic_voice.domain.scoring import id_recall, silence_output, term_recall

STUBS: list[Callable[[], object]] = [
    lambda: term_recall("x", "x", ["x"]),
    lambda: id_recall("1234", "1234"),
    lambda: silence_output(""),
]


@pytest.mark.parametrize("call", STUBS)
def test_the_scorers_are_stubs_until_track_a(call: Callable[[], object]) -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        call()
