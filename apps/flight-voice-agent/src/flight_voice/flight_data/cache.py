"""A short cache of a live source's answers (`CachedFlightData`), so the same day asked again in
a call (a second `find_flights` for the way back, the same day with an airline) answers at once.

`day(q)` is keyed by `q.key()`. A fresh entry (younger than `ttl_s`) is returned at once; a
fetch already running for that key is shared, awaited through `asyncio.shield`, so a caller who
barges in never cancels another caller's fetch (nor its own, which still fills the cache).
Answers are stored, `no_flights` included, at most `max_entries` (the least recently used
dropped first); a failure never is: its fetch is forgotten, so the next ask tries again, and a
done-callback retrieves its error. `days(q)` asks the inner source's fare calendar first (not
for a span asked `each_day`), kept the same way under the span's key (`SpanQuery.key()`, the
same `ttl_s`; a calendar that priced no day is kept too, as that answer), and when it gives
none, reads the span through the cache's own `day`, with the inner source's cut, concurrency
and deadline, so a span fills each day's entry. `name`, `span_days`, `last_day` and `nearest`
are the inner source's; `aclose` cancels the fetches still running and closes it.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import date

from flight_voice.flight_data.fanout import Spanning
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery

__all__ = ["CachedFlightData"]


class _Store[T]:
    """Answers by key (the module's docstring): fresh ones kept, running fetches shared."""

    def __init__(self, ttl_s: float, clock: Callable[[], float], max_entries: int) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._max = max_entries
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._running: dict[str, asyncio.Task[T]] = {}

    async def get(self, key: str, fetch: Callable[[], Awaitable[T]]) -> T:
        """The answer for `key`: stored, shared with a fetch running, or fetched now."""
        held = self._entries.get(key)
        if held is not None:
            if self._clock() - held[0] < self._ttl_s:
                self._entries.move_to_end(key)
                return held[1]
            del self._entries[key]
        task = self._running.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch(key, fetch))
            self._running[key] = task
            task.add_done_callback(lambda done: self._settled(key, done))
        return await asyncio.shield(task)

    async def cancel(self) -> None:
        """Cancel the fetches still running."""
        running = list(self._running.values())
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def _fetch(self, key: str, fetch: Callable[[], Awaitable[T]]) -> T:
        answer = await fetch()
        self._entries[key] = (self._clock(), answer)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
        return answer

    def _settled(self, key: str, done: asyncio.Task[T]) -> None:
        if self._running.get(key) is done:
            del self._running[key]
        if not done.cancelled():
            done.exception()  # retrieved, so a failure nobody awaited is not reported


class CachedFlightData:
    """`inner` behind a cache (the module's docstring); `clock` is monotonic seconds."""

    def __init__(
        self,
        inner: Spanning,
        *,
        ttl_s: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 256,
    ) -> None:
        self._inner = inner
        self._days: _Store[DayOffers] = _Store(ttl_s, clock, max_entries)
        self._calendars: _Store[DayFares | None] = _Store(ttl_s, clock, max_entries)

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def span_days(self) -> int:
        return self._inner.span_days

    def last_day(self, today: date) -> date:
        return self._inner.last_day(today)

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        return await self._inner.nearest(q, today)

    async def day(self, q: OfferQuery) -> DayOffers:
        """The answer to `q`: stored, shared with a fetch running, or fetched now."""
        return await self._days.get(q.key(), lambda: self._inner.day(q))

    async def calendar(self, q: SpanQuery) -> DayFares | None:
        """The inner source's fare calendar for `q`, through the cache."""
        return await self._calendars.get(q.key(), lambda: self._inner.calendar(q))

    async def days(self, q: SpanQuery) -> DayFares:
        """The span: the calendar's, else each day through the cache; each day at once when
        it asks `each_day`."""
        found = None if q.each_day else await self.calendar(q)
        return found if found is not None else await self._inner.span(self.day, q)

    async def aclose(self) -> None:
        """Cancel the fetches still running, then close the inner source."""
        await self._days.cancel()
        await self._calendars.cancel()
        await self._inner.aclose()
