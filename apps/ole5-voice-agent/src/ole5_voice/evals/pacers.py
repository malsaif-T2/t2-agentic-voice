"""The pacers of a timing run (plan 003's registration, T): at most `limit` requests to one model
in any minute, held between variants, since a variant's requests go from inside its call.

Before a variant the run asks each model's pacer for room for the most that variant may send
(`room_for`), and after it counts what it sent (`count`), stamped when the variant ended: no
later than each request went, so a request stays in the window at least as long as it should,
and the window never holds more than `limit` while each variant sends no more than it asked
room for. The phrase cache's requests at the run's start are counted the same way, before the
first variant.
"""

from __future__ import annotations

from collections import deque

from ole5_voice.evals.groq_answerer import Clock, Sleep

WINDOW_S = 60.0  # a minute, as Groq's per-minute limits count (console.groq.com/docs/rate-limits)


class MinutePacer:
    """At most `limit` requests in any `WINDOW_S` seconds, on `clock`, waiting with `sleep`."""

    def __init__(self, limit: int, clock: Clock, sleep: Sleep) -> None:
        if limit < 1:
            raise ValueError("a pacer allows at least one request a minute")
        self.limit = limit
        self._clock, self._sleep = clock, sleep
        self._sent: deque[float] = deque()  # when each request in the window was counted

    def in_window(self) -> int:
        """The requests counted in the last `WINDOW_S` seconds."""
        now = self._clock()
        while self._sent and self._sent[0] <= now - WINDOW_S:
            self._sent.popleft()
        return len(self._sent)

    async def room_for(self, requests: int) -> None:
        """Return once `requests` more fit in the window; ValueError for more than `limit`,
        which never fit."""
        if requests > self.limit:
            raise ValueError(f"{requests} requests never fit in a window of {self.limit}")
        while self.in_window() + requests > self.limit:
            # The oldest request that must leave the window for these to fit.
            leaving = self._sent[self.in_window() + requests - self.limit - 1]
            await self._sleep(max(leaving + WINDOW_S - self._clock(), 0.0) + 1e-3)

    def count(self, requests: int) -> None:
        """Count `requests` sent, now."""
        self._sent.extend([self._clock()] * requests)
