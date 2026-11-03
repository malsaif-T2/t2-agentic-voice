"""The session's overlaps (voice/session/overlap.py): an overlap's state, and the overlaps a stub
until plan 005's Track B builds them, whose tests drive the session through the fake I/O."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState, call_words
from t2_agentic_voice.voice.session.session_events import Transcribed

from tests.t2_agentic_voice.session_fakes import FakeSessionIO

HEARD = Transcribed(turn_id=0, at=2.0, audio_s=0.75, sent_at=1.8, transcript=None, part="window")


def test_an_overlap_starts_undecided() -> None:
    state = OverlapState(turn_id=0, reply_id=1, speech_at=1.0, ducked_at=1.34)
    assert (state.window, state.overlap, state.decided) == (None, None, None)
    state.decided = Verdict(action="stop", kind="stop", reason="stop_word")
    assert state.decided.action == "stop"


@pytest.mark.parametrize(
    "step",
    [
        lambda overlaps: overlaps.open(0, reply_id=1, speech_at=1.0, at=1.34),
        lambda overlaps: overlaps.judge(HEARD, played=("a made-up clause",)),
        lambda overlaps: overlaps.get(0),
        lambda overlaps: overlaps.open_turns,
    ],
)
def test_the_overlaps_are_a_stub_until_they_are_built(
    settings: VoiceSettings, step: Callable[[Overlaps], object]
) -> None:
    setup = FakeSessionIO(settings).setup
    with pytest.raises(NotImplementedError, match="Track B"):
        step(Overlaps(setup))
    with pytest.raises(NotImplementedError, match="Track B"):
        call_words(setup)
