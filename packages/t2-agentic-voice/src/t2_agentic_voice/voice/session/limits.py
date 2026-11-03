"""The session's own timers (plan 003, Q4), for one call's session (voice/session/call.py): the
call's length, `limits.max_call_s` from its start, and the time with nothing heard from the caller,
`limits.idle_s`, which a turn's opening or closing starts again. Each is a deadline on the call's
clock that a task of its own sleeps until; once it passes, the session's `reached` runs (the
`ended` notice, then the end), unless the call has ended or is ending (`over`), and the timer
sleeps again when `reached` moved the deadline on (`idle` holds off while a turn is open).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from t2_agentic_voice.voice.session.io import CallSetup

# The session's own timers: the call's length, and the time with nothing heard (plan 003, Q4).
Limit = Literal["max_call", "idle"]


class CallLimits:
    """One call's limits: each one's deadline, and the timers that sleep until them."""

    def __init__(
        self,
        setup: CallSetup,
        *,
        over: Callable[[], bool],
        reached: Callable[[Limit], Awaitable[None]],
    ) -> None:
        self._clock, self._limits = setup.clock, setup.settings.limits
        self._over, self._reached = over, reached
        self._deadlines: dict[Limit, float] = {}
        self._timers: list[asyncio.Task[None]] = []

    def start(self, at: float) -> None:
        """The call connected at `at`: each limit's deadline from then, and its timer started."""
        limits = self._limits
        self._deadlines = {"max_call": at + limits.max_call_s, "idle": at + limits.idle_s}
        self._timers = [asyncio.create_task(self._timer(limit)) for limit in self._deadlines]

    def heard(self, at: float) -> None:
        """The caller was heard at `at`: the time with nothing heard starts again."""
        self._deadlines["idle"] = at + self._limits.idle_s

    def passed(self, limit: Limit, now: float) -> bool:
        """Whether `limit`'s deadline has passed at `now`."""
        return now >= self._deadlines[limit]

    def stop(self) -> None:
        """The call ended: every timer stops, but the one running this step."""
        for task in self._timers:
            if task is not asyncio.current_task():
                task.cancel()

    async def aclose(self) -> None:
        """The call's stream ended: every timer stops, and is awaited."""
        for task in self._timers:
            task.cancel()
        await asyncio.gather(*self._timers, return_exceptions=True)

    async def _timer(self, limit: Limit) -> None:
        """Sleep until `limit`'s deadline, which hearing the caller moves for `idle`; then ask
        the session, once."""
        clock = self._clock
        while not self._over():
            wait = self._deadlines[limit] - clock.now()
            if wait > 0:
                await clock.sleep(wait)
                continue
            await self._reached(limit)
            if self._deadlines[limit] <= clock.now():
                return
