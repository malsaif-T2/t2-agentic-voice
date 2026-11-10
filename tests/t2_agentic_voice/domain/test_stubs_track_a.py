"""The stubs plan 007's Block 0 left for Track A, each raising with the track's name. Track A
deletes this file as it fills them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.domain.action_flow import advance
from t2_agentic_voice.domain.action_lines import default_action_lines
from t2_agentic_voice.domain.claims import check_claims, default_claims

STUBS: dict[str, Callable[[], Any]] = {
    "advance": lambda: advance("confirming", "yes"),
    "check_claims": lambda: check_claims(
        "made up", claims={}, any_action=(), evidence=(), settings=GuardSettings(), year=2026
    ),
    "default_claims": lambda: default_claims("en"),
    "default_action_lines": lambda: default_action_lines("en"),
}


@pytest.mark.parametrize("call", STUBS.values(), ids=STUBS.keys())
def test_a_stub_raises_naming_track_a(call: Callable[[], Any]) -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        call()
