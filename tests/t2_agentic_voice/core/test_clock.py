"""A call's clock lives in core (core/clock.py), so the talker and the tool runner, which may not
import voice (harness.toml [layers]), time their work on the clock the session runs on; the
session's I/O (voice/session/io.py) gives the same names."""

from __future__ import annotations

import t2_agentic_voice.voice.session.io as session_io
from t2_agentic_voice.core import clock


def test_the_calls_clock_is_cores_and_the_sessions_io_gives_the_same_one() -> None:
    assert session_io.Clock is clock.Clock
    assert session_io.SystemClock is clock.SystemClock
    assert session_io.SYSTEM_CLOCK is clock.SYSTEM_CLOCK
    assert isinstance(clock.SYSTEM_CLOCK, clock.SystemClock)
