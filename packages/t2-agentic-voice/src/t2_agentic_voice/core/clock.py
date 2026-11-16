"""A call's clock, in core so that every layer timing a call's work reads the one clock the call
runs on (harness.toml [layers]): the voice session its events' times and its timers
(voice/session/io.py gives these names too), and the talker and the tool runner, which may not
import voice, a tool's progress time and its timeout, a model request's first token, and the
prompt's date. A real call runs on `SYSTEM_CLOCK`; a test, `TextCall` among them, on a clock that
moves only when the test moves it. A call held on a pinned day (`TextCall(today=...)`,
`AudioCall(today=...)`) runs on its clock moved by whole days (`day_shift`, `DatedClock`), so the
prompt's date is that day in the agent's time zone and every time of day stays as it was.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime, timedelta, tzinfo
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


def day_shift(wall: datetime, today: date, zone: tzinfo) -> timedelta:
    """The whole days that move `wall` to a time on `today` in `zone`, its time of day kept."""
    return today - wall.astimezone(zone).date()


class DatedClock:
    """`inner`, its `wall` moved by whole days so that, as it is built, its date in `zone` is
    `today` (`day_shift`); its `now` and `sleep` are `inner`'s."""

    def __init__(self, inner: Clock, today: date, zone: tzinfo) -> None:
        self._inner = inner
        self._shift = day_shift(inner.wall(), today, zone)

    def now(self) -> float:
        return self._inner.now()

    def wall(self) -> datetime:
        return self._inner.wall() + self._shift

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)
