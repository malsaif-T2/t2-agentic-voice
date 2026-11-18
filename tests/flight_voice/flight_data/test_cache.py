"""The cache of a live source's answers (flight_data/cache.py), on a fake clock: an entry lives
`ttl_s`, one fetch serves every caller of the same day, a failure is never stored, a caller who
is cancelled does not cancel the shared fetch, the least recently used entry goes first, a span
fills each day's entry, and `aclose` cancels what is running and closes the source."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from flight_voice.flight_data.cache import CachedFlightData
from flight_voice.flight_data.fanout import DayFn, span_of
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery

from tests.flight_voice.flight_data.serpapi_support import DAY, Clock, offers, query


class Inner:
    """A live source's stand-in: counts each day fetched, waits on `gate` when set, and fails
    while `failing`."""

    name = "serpapi"
    span_days = 3

    def __init__(self) -> None:
        self.fetched: list[str] = []
        self.gate: asyncio.Event | None = None
        self.failing = False
        self.closed = False

    def last_day(self, today: date) -> date:
        return today + timedelta(330)

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        return ()

    async def day(self, q: OfferQuery) -> DayOffers:
        self.fetched.append(q.key())
        if self.gate is not None:
            await self.gate.wait()
        if self.failing:
            raise FlightDataUnavailableError("day", "http_error", 503)
        return offers(q, 900 + len(self.fetched))

    async def days(self, q: SpanQuery) -> DayFares:
        return await self.span(self.day, q)

    async def span(self, day_fn: DayFn, q: SpanQuery) -> DayFares:
        return await span_of(day_fn, q, span_days=self.span_days, concurrency=3, deadline_s=1)

    async def aclose(self) -> None:
        self.closed = True


def _cached(*, ttl_s: float = 600, max_entries: int = 256) -> tuple[CachedFlightData, Inner, Clock]:
    inner, clock = Inner(), Clock()
    cache = CachedFlightData(inner, clock=clock, ttl_s=ttl_s, max_entries=max_entries)
    return cache, inner, clock


def test_an_entry_lives_its_ttl() -> None:
    cache, inner, clock = _cached(ttl_s=600)

    async def scene() -> list[int]:
        prices = [(await cache.day(query())).offers[0].price.amount]
        clock.now += 599
        prices.append((await cache.day(query())).offers[0].price.amount)
        clock.now += 2
        prices.append((await cache.day(query())).offers[0].price.amount)
        return prices

    assert asyncio.run(scene()) == [901, 901, 902]
    assert len(inner.fetched) == 2


def test_one_fetch_serves_every_caller_of_the_same_day() -> None:
    cache, inner, _ = _cached()

    async def scene() -> list[DayOffers]:
        inner.gate = asyncio.Event()
        callers = [asyncio.create_task(cache.day(query())) for _ in range(3)]
        await asyncio.sleep(0.01)
        inner.gate.set()
        return list(await asyncio.gather(*callers))

    answers = asyncio.run(scene())
    assert len(inner.fetched) == 1 and answers[0] == answers[1] == answers[2]


def test_a_failure_is_never_stored() -> None:
    cache, inner, _ = _cached()

    async def scene() -> DayOffers:
        inner.failing = True
        with pytest.raises(FlightDataUnavailableError):
            await cache.day(query())
        inner.failing = False
        return await cache.day(query())

    assert asyncio.run(scene()).status == "ok"
    assert len(inner.fetched) == 2


def test_a_cancelled_caller_does_not_cancel_the_shared_fetch() -> None:
    cache, inner, _ = _cached()

    async def scene() -> DayOffers:
        inner.gate = asyncio.Event()
        first = asyncio.create_task(cache.day(query()))
        second = asyncio.create_task(cache.day(query()))
        await asyncio.sleep(0.01)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        inner.gate.set()
        answer = await second
        assert await cache.day(query()) == answer  # stored, though its first caller left
        return answer

    assert asyncio.run(scene()).status == "ok"
    assert len(inner.fetched) == 1


def test_a_lone_cancelled_caller_still_fills_the_cache() -> None:
    cache, inner, _ = _cached()

    async def scene() -> None:
        inner.gate = asyncio.Event()
        only = asyncio.create_task(cache.day(query()))
        await asyncio.sleep(0.01)
        only.cancel()
        with pytest.raises(asyncio.CancelledError):
            await only
        inner.gate.set()
        await asyncio.sleep(0.01)
        inner.gate = None
        await cache.day(query())

    asyncio.run(scene())
    assert len(inner.fetched) == 1


def test_the_least_recently_used_entry_goes_first() -> None:
    cache, inner, _ = _cached(max_entries=2)
    days = [query(DAY + timedelta(n)) for n in range(3)]

    async def scene() -> None:
        await cache.day(days[0])
        await cache.day(days[1])
        await cache.day(days[0])  # used again: days[1] is now the oldest
        await cache.day(days[2])
        await cache.day(days[0])
        await cache.day(days[1])

    asyncio.run(scene())
    assert inner.fetched == [days[0].key(), days[1].key(), days[2].key(), days[1].key()]


def test_a_span_fills_each_days_entry_and_the_inner_cut_holds() -> None:
    cache, inner, _ = _cached()
    q = query()
    span = SpanQuery(origin=q.origin, destination=q.destination, first=DAY, last=DAY + timedelta(5))

    async def scene() -> DayFares:
        fares = await cache.days(span)
        for n in range(3):
            await cache.day(query(DAY + timedelta(n)))
        return fares

    fares = asyncio.run(scene())
    assert len(fares.days) == 3 and fares.checked_last == DAY + timedelta(2)
    assert len(inner.fetched) == 3


def test_the_inner_sources_facts_are_passed_on_and_aclose_cancels_and_closes() -> None:
    cache, inner, _ = _cached()
    today = date(2026, 11, 18)
    assert (cache.name, cache.span_days, cache.last_day(today)) == (
        "serpapi",
        3,
        today + timedelta(330),
    )

    async def scene() -> None:
        assert await cache.nearest(query(), today) == ()
        inner.gate = asyncio.Event()
        waiting = asyncio.create_task(cache.day(query()))
        await asyncio.sleep(0.01)
        await cache.aclose()
        with pytest.raises(asyncio.CancelledError):
            await waiting

    asyncio.run(scene())
    assert inner.closed
