"""The hold's signals for the early start (voice/turn_hold.py; plan 006, Block 0, Q2): that Smart
Turn called the turn complete and the hold began, and that the caller resumed within it. Track C
builds them; until then each is a stub that raises, and nothing calls them, so a turn's end is
as voice/test_turn_hold.py pins it."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.voice.turn_hold import HeldTurnStop

from tests.t2_agentic_voice.voice.kit import PauseAnalyzer


def test_the_holds_signals_are_stubs() -> None:
    stop = HeldTurnStop(hold_s=0.6, turn_analyzer=PauseAnalyzer(), wait_for_transcript=False)
    assert not stop.decision_scheduled
    with pytest.raises(NotImplementedError):
        asyncio.run(stop.hold_began())
    with pytest.raises(NotImplementedError):
        asyncio.run(stop.hold_resumed())
