"""The stubs plan 007's Block 0 left for Track A, each raising with the track's name. Track A
deletes this file as it fills them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from t2_agentic_voice.domain.action_lines import default_action_lines

STUBS: dict[str, Callable[[], Any]] = {
    "default_action_lines": lambda: default_action_lines("en"),
}


@pytest.mark.parametrize("call", STUBS.values(), ids=STUBS.keys())
def test_a_stub_raises_naming_track_a(call: Callable[[], Any]) -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        call()
