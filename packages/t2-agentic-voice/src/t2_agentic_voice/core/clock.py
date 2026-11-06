"""A call's clock, in core so that every layer timing a call's work reads the one clock the call
runs on (harness.toml [layers]): the voice session its events' times and its timers
(voice/session/io.py gives these names too), and the talker and the tool runner, which may not
import voice, a tool's progress time and its timeout, a model request's first token, and the
prompt's date. A real call runs on `SYSTEM_CLOCK`; a test, `TextCall` among them, on a clock that
moves only when the test moves it.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """A call's time: `now`, on the scale every event's `at` is on; `wall`, the time of day the
    public events and the report carry; and `sleep`, for the session's timers."""

    def now(self) -> float:
        """Seconds on a monotonic scale with no fixed start."""

    def wall(self) -> datetime:
        """The time of day now, aware (UTC)."""

    async def sleep(self, seconds: float) -> None:
        """Return once `seconds` have passed on this clock."""


class SystemClock:
    """The clock of a real call: `time.perf_counter`, whose resolution is far finer than
    `time.monotonic`'s 15.6 ms on Windows (plan 003's decision log), the system's UTC time, and
    asyncio's sleep."""

    def now(self) -> float:
        return time.perf_counter()

    def wall(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


SYSTEM_CLOCK = SystemClock()
