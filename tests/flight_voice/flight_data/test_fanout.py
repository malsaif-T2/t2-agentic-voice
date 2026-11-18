"""A span read one day at a time (flight_data/fanout.py): at most `concurrency` days at once, a
partial answer at the deadline with the late days unknown, a day with no flights known with no
price, and a span where every day failed raised, `lasting` when any day's failure was."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from flight_voice.flight_data.fanout import cut, fan_out, span_of
from flight_voice.flight_data.model import Money
from flight_voice.flight_data.port import Failure, FlightDataUnavailableError
from flight_voice.flight_data.queries import DayOffers, OfferQuery, SpanQuery

from tests.flight_voice.flight_data.serpapi_support import offers as _offers
from tests.flight_voice.flight_data.serpapi_support import query

FIRST = date(2026, 11, 19)


def _span(days: int) -> SpanQuery:
    q = query()
    return SpanQuery(
        origin=q.origin, destination=q.destination, first=FIRST, last=FIRST + timedelta(days - 1)
    )


def test_at_most_concurrency_days_run_at_once() -> None:
    running, most = 0, 0

    async def day(q: OfferQuery) -> DayOffers:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        running -= 1
        return _offers(q, 900 + q.day.day, 1200)

    fares = asyncio.run(fan_out(day, _span(10), concurrency=3, deadline_s=5))
    assert most == 3
    assert [f.day for f in fares.days] == [FIRST + timedelta(i) for i in range(10)]
    assert fares.days[0].lowest == Money(amount=919) and fares.days[0].flights == 2
    assert fares.status == "ok" and fares.checked_last is None


def test_a_partial_answer_at_the_deadline_leaves_the_late_days_unknown() -> None:
    cancelled: list[date] = []

    async def day(q: OfferQuery) -> DayOffers:
        if q.day.day % 2:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(q.day)
                raise
        return _offers(q) if q.day.day == 20 else _offers(q, 899)

    fares = asyncio.run(fan_out(day, _span(4), concurrency=4, deadline_s=0.1))
    assert [(f.known, f.lowest) for f in fares.days] == [
        (False, None),
        (True, None),
        (False, None),
        (True, Money(amount=899)),
    ]
    assert sorted(cancelled) == [FIRST, FIRST + timedelta(2)]


def test_a_failed_day_is_unknown_never_no_flights() -> None:
    async def day(q: OfferQuery) -> DayOffers:
        if q.day == FIRST:
            raise FlightDataUnavailableError("day", "http_error", 503)
        return _offers(q, 1000)

    fares = asyncio.run(fan_out(day, _span(2), concurrency=2, deadline_s=1))
    assert [f.known for f in fares.days] == [False, True]


def test_a_span_with_no_flights_on_any_day_it_knows_is_no_flights() -> None:
    async def day(q: OfferQuery) -> DayOffers:
        return _offers(q)

    assert asyncio.run(fan_out(day, _span(2), concurrency=2, deadline_s=1)).status == "no_flights"


@pytest.mark.parametrize(
    ("failures", "failure", "lasting"),
    [
        (["http_error", "rate_limited", "timeout"], "rate_limited", True),
        (["http_error", "connection", "timeout"], "http_error", False),
    ],
)
def test_every_day_failed_raises_and_passes_lasting_on(
    failures: list[Failure], failure: str, lasting: bool
) -> None:
    async def day(q: OfferQuery) -> DayOffers:
        raise FlightDataUnavailableError("day", failures[(q.day - FIRST).days])

    with pytest.raises(FlightDataUnavailableError) as failed:
        asyncio.run(fan_out(day, _span(3), concurrency=3, deadline_s=1))
    assert (failed.value.step, failed.value.failure, failed.value.lasting) == (
        "days",
        failure,
        lasting,
    )


def test_every_day_late_is_a_timeout() -> None:
    async def day(q: OfferQuery) -> DayOffers:
        await asyncio.sleep(10)
        raise AssertionError  # pragma: no cover

    with pytest.raises(FlightDataUnavailableError) as failed:
        asyncio.run(fan_out(day, _span(2), concurrency=2, deadline_s=0.05))
    assert failed.value.failure == "timeout"


def test_a_bug_in_a_day_propagates() -> None:
    async def day(q: OfferQuery) -> DayOffers:
        raise KeyError("a bug")

    with pytest.raises(KeyError):
        asyncio.run(fan_out(day, _span(2), concurrency=2, deadline_s=1))


def test_a_cancelled_span_cancels_every_day() -> None:
    cancelled = 0

    async def day(q: OfferQuery) -> DayOffers:
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled += 1
            raise
        raise AssertionError  # pragma: no cover

    async def scene() -> None:
        task = asyncio.create_task(fan_out(day, _span(3), concurrency=3, deadline_s=5))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scene())
    assert cancelled == 3


def test_a_span_is_cut_to_span_days_and_keeps_the_span_asked() -> None:
    q = _span(20)
    kept, last = cut(q, 14)
    assert (kept.first, kept.last, last) == (FIRST, FIRST + timedelta(13), FIRST + timedelta(13))
    assert cut(_span(14), 14) == (_span(14), None)

    async def day(one: OfferQuery) -> DayOffers:
        return _offers(one, 500)

    fares = asyncio.run(span_of(day, q, span_days=14, concurrency=14, deadline_s=1))
    assert fares.query == q and fares.checked_last == FIRST + timedelta(13)
    assert len(fares.days) == 14
