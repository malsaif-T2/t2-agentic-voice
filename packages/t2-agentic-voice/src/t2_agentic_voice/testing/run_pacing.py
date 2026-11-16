"""The pacing of a measurement run that spends: at most a model's requests and tokens in any
minute, and its requests of the day, as a provider's key allows them.

`MinutePacer` holds one count in any `WINDOW_S` seconds: before a step the run asks it for room
for the most that step may send (`room_for`), and after it counts what it sent (`count`), stamped
no later than each request went, so a request stays in the window at least as long as it should.
`ModelPacer` holds one model's `Limits`: its requests and its tokens a minute, each a
`MinutePacer`, and its requests of the day, from the day's count so far (`requests_today`, which
reads every app's run history, since one key's day is shared), refused at the limit
(`DailyLimitError`). Both run on a `RunClock` and wait with a `RunSleep`, which a test replaces
with a clock that moves only when it sleeps. Public through the `evals` facade.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

# Seconds, from any start: `time.perf_counter`, monotonic and fine.
type RunClock = Callable[[], float]
# A wait of so many seconds: `asyncio.sleep`.
type RunSleep = Callable[[float], Awaitable[None]]
# A minute, as Groq's per-minute limits count (console.groq.com/docs/rate-limits).
WINDOW_S: Final = 60.0


class DailyLimitError(Exception):
    """The next request would pass the key's daily limit for its model."""

    def __init__(self, model: str, used: int, limit: int) -> None:
        super().__init__(f"{model}: {used} of {limit} requests today")
        self.model, self.used, self.limit = model, used, limit


class MinutePacer:
    """At most `limit` requests in any `WINDOW_S` seconds, on `clock`, waiting with `sleep`."""

    def __init__(self, limit: int, clock: RunClock, sleep: RunSleep) -> None:
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

    async def room_for(self, requests: int) -> float:
        """Return once `requests` more fit in the window, with the seconds it waited for them;
        ValueError for more than `limit`, which never fit."""
        if requests > self.limit:
            raise ValueError(f"{requests} requests never fit in a window of {self.limit}")
        waited = 0.0
        while self.in_window() + requests > self.limit:
            # The oldest request that must leave the window for these to fit.
            leaving = self._sent[self.in_window() + requests - self.limit - 1]
            wait = max(leaving + WINDOW_S - self._clock(), 0.0) + 1e-3
            waited += wait
            await self._sleep(wait)
        return waited

    def count(self, requests: int) -> None:
        """Count `requests` sent, now."""
        self._sent.extend([self._clock()] * requests)


@dataclass(frozen=True)
class Limits:
    """A model's limits on the key: requests and tokens a minute, and requests a day."""

    rpm: int
    tpm: int
    rpd: int


class ModelPacer:
    """One model's limits held: the requests and the tokens in any minute, and the requests of
    the day, starting from `used_today`."""

    def __init__(
        self, limits: Limits, *, used_today: int, clock: RunClock, sleep: RunSleep
    ) -> None:
        self.limits = limits
        self.today = used_today
        self._requests = MinutePacer(limits.rpm, clock, sleep)
        self._tokens = MinutePacer(limits.tpm, clock, sleep)

    async def room(self, model: str, tokens: int) -> float:
        """Return once one more request of `tokens` fits the minute, with the seconds it waited;
        DailyLimitError when it would pass the day's limit."""
        if self.today >= self.limits.rpd:
            raise DailyLimitError(model, self.today, self.limits.rpd)
        return await self.ahead(1, tokens)

    async def ahead(self, requests: int, tokens: int) -> float:
        """Return once `requests` more requests of `tokens` each fit the minute (as many as it
        holds), with the seconds it waited; nothing is counted."""
        waited = await self._requests.room_for(min(requests, self.limits.rpm))
        return waited + await self._tokens.room_for(min(requests * tokens, self.limits.tpm))

    def sent(self) -> None:
        """Count one request sent, now."""
        self._requests.count(1)
        self.today += 1

    def used(self, tokens: int) -> None:
        """Count the tokens a request used, now that they are known."""
        self._tokens.count(tokens)
