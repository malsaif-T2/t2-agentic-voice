"""A span of days read one day at a time, for a source with no calendar of its own (SerpApi):
`fan_out` and `span_of`, which cuts the span to the source's `span_days` first.

One task a day, at most `concurrency` at once, all under one `deadline_s`; a day still running
then is cancelled and unknown (a cache's shielded fetch keeps running and fills the cache). A
day with offers gives its lowest price and how many it lists; a day with none, no price; a day
that failed or ran out of time is `known=False`. The answer is `no_flights` when no day it knows
has a flight, else `ok`. Only a span where every day failed raises, `lasting` when any day's
failure was. A cancellation (the caller barging in) cancels every day and propagates; an error
that is not the port's (a bug) propagates too.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, timedelta
from typing import Protocol

from flight_voice.flight_data.model import Money
from flight_voice.flight_data.port import FlightData, FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFare, DayFares, DayOffers, OfferQuery, SpanQuery

__all__ = ["DayFn", "Spanning", "cut", "fan_out", "span_of"]

type DayFn = Callable[[OfferQuery], Awaitable[DayOffers]]


class Spanning(FlightData, Protocol):
    """A source that fans a span out, as a cache over it needs: `span(day_fn, q)` reads the
    span through `day_fn` (the cache's `day`) with the source's own cut, concurrency and
    deadline."""

    async def span(self, day_fn: DayFn, q: SpanQuery) -> DayFares: ...


def cut(q: SpanQuery, span_days: int) -> tuple[SpanQuery, date | None]:
    """`q` cut to its first `span_days` days, and the last day kept when it was cut."""
    last = q.first + timedelta(days=span_days - 1)
    if q.last <= last:
        return q, None
    return q.model_copy(update={"last": last}), last


async def span_of(
    day_fn: DayFn, q: SpanQuery, *, span_days: int, concurrency: int, deadline_s: float
) -> DayFares:
    """`q` cut to `span_days` (its `checked_last` then set), then fanned out; the answer keeps
    the span asked for as its query."""
    kept, last = cut(q, span_days)
    fares = await fan_out(day_fn, kept, concurrency=concurrency, deadline_s=deadline_s)
    return fares.model_copy(update={"query": q, "checked_last": last})


async def fan_out(day_fn: DayFn, q: SpanQuery, *, concurrency: int, deadline_s: float) -> DayFares:
    """Each day of `q` through `day_fn` (the module's docstring)."""
    gate = asyncio.Semaphore(concurrency)

    async def one(day: date) -> DayOffers:
        async with gate:
            return await day_fn(q.day(day))

    days = q.dates()
    tasks = [asyncio.create_task(one(d)) for d in days]
    try:
        await asyncio.wait(tasks, timeout=deadline_s)
    finally:
        late = [t for t in tasks if not t.done()]
        for task in late:
            task.cancel()
        if late:
            await asyncio.gather(*late, return_exceptions=True)
    return _fares(q, days, tasks)


def _fares(
    q: SpanQuery, days: Sequence[date], tasks: Sequence[asyncio.Task[DayOffers]]
) -> DayFares:
    fares: list[DayFare] = []
    failures: list[FlightDataUnavailableError] = []
    for day, task in zip(days, tasks, strict=True):
        error = None if task.cancelled() else task.exception()
        if error is not None and not isinstance(error, FlightDataUnavailableError):
            raise error  # a bug, not the source failing
        if task.cancelled() or error is not None:
            fares.append(DayFare(day=day, known=False))
            if isinstance(error, FlightDataUnavailableError):
                failures.append(error)
            continue
        fares.append(_fare(day, task.result()))
    if not any(f.known for f in fares):
        raise _every_day_failed(failures)
    with_flights = any(f.lowest is not None for f in fares)
    return DayFares(query=q, status="ok" if with_flights else "no_flights", days=tuple(fares))


def _fare(day: date, answer: DayOffers) -> DayFare:
    if not answer.offers:
        return DayFare(day=day)
    lowest = min(o.price.amount for o in answer.offers)
    return DayFare(day=day, lowest=Money(amount=lowest), flights=len(answer.offers))


def _every_day_failed(failures: Sequence[FlightDataUnavailableError]) -> FlightDataUnavailableError:
    """The span's error: a lasting day's failure when there is one, else the first day's, else
    a timeout (every day ran out of time)."""
    lasting = [f for f in failures if f.lasting]
    if not failures:
        return FlightDataUnavailableError("days", "timeout")
    chosen = (lasting or list(failures))[0]
    return FlightDataUnavailableError("days", chosen.failure, chosen.status)
