"""The SerpApi adapter (flight_data/serpapi.py) on httpx's MockTransport: the exact params, the
airports of a city joined by commas; one retry after a connect error or a fast 503, none after a
read timeout, a 401, a 429 or a 500 that came late; the deadline held; the hold-off after a
rejected key; `lasting`; the key in no log line, error, detail or chain; a cancellation
propagates; and a span cut to `span_days`."""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta

import httpx
import pytest
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFares, DayOffers, SpanQuery
from flight_voice.flight_data.serpapi import (
    HOLD_OFF_S,
    LAST_DAY_DAYS,
    NOT_RECORDED_HEADER,
    SerpApiFlightData,
)

from tests.flight_voice.flight_data.serpapi_support import (
    DAY,
    KEY,
    Clock,
    Handler,
    adapter,
    answering,
    body,
    content,
    query,
)
from tests.leaks import holding, shown


class Wire:
    """A handler that answers from a list of steps, one a request, and keeps each request."""

    def __init__(self, *steps: Handler) -> None:
        self.steps = list(steps)
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return await step(request)


def _raising(error: type[httpx.RequestError]) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise error("made up", request=request)

    return handler


def _day(source: SerpApiFlightData, *, close: bool = True) -> DayOffers:
    async def one() -> DayOffers:
        try:
            return await source.day(query())
        finally:
            if close:
                await source.aclose()

    return asyncio.run(one())


def _failure(source: SerpApiFlightData) -> FlightDataUnavailableError:
    with pytest.raises(FlightDataUnavailableError) as failed:
        _day(source)
    return failed.value


def test_one_day_sends_the_exact_params() -> None:
    wire = Wire(answering())
    answer = _day(adapter(wire))
    assert answer.status == "ok" and len(answer.offers) == 11
    (request,) = wire.requests
    assert (request.method, request.url.host, request.url.path) == ("GET", "serpapi.com", "/search")
    assert dict(request.url.params) == {
        "engine": "google_flights",
        "api_key": KEY,
        "type": "2",
        "departure_id": "RUH",
        "arrival_id": "JED",
        "outbound_date": "2026-11-19",
        "travel_class": "1",
        "adults": "1",
        "currency": "SAR",
        "gl": "sa",
        "hl": "en",
        "stops": "2",
    }


def test_a_citys_airports_are_joined_by_commas_and_deep_search_is_asked_when_set() -> None:
    wire = Wire(answering(value=body() | {"best_flights": [], "other_flights": []}))
    source = adapter(wire, deep_search=True)
    q = query(origin="London", destination="Dubai").model_copy(
        update={"cabin": "business", "adults": 2}
    )

    async def one() -> DayOffers:
        try:
            return await source.day(q)
        finally:
            await source.aclose()

    assert asyncio.run(one()).status == "no_flights"
    params = wire.requests[0].url.params
    assert (params["departure_id"], params["arrival_id"]) == ("LHR,LGW,STN", "DXB,DWC")
    assert (params["travel_class"], params["adults"], params["deep_search"]) == ("3", "2", "true")
    assert "no_cache" not in params


@pytest.mark.parametrize(
    "first",
    [_raising(httpx.ConnectError), _raising(httpx.ConnectTimeout), answering(503)],
)
def test_one_retry_after_a_quick_failure(first: Handler) -> None:
    wire = Wire(first, answering())
    assert _day(adapter(wire)).status == "ok"
    assert len(wire.requests) == 2


def test_no_second_retry() -> None:
    wire = Wire(answering(503))
    failure = _failure(adapter(wire))
    assert (failure.failure, failure.status, len(wire.requests)) == ("http_error", 503, 2)


@pytest.mark.parametrize(
    ("first", "failure", "status"),
    [
        (_raising(httpx.ReadTimeout), "timeout", None),
        (answering(401), "rejected_key", 401),
        (answering(403), "rejected_key", 403),
        (answering(429), "rate_limited", 429),
        (answering(400), "http_error", 400),
        (answering(404), "http_error", 404),
        (_raising(httpx.ReadError), "connection", None),
    ],
)
def test_no_retry_after_a_slow_failure_or_a_refusal(
    first: Handler, failure: str, status: int | None
) -> None:
    wire = Wire(first, answering())
    error = _failure(adapter(wire))
    assert (error.failure, error.status, len(wire.requests)) == (failure, status, 1)
    assert error.lasting is (failure in ("rejected_key", "rate_limited"))
    assert error.__cause__ is None and error.__context__ is None


def test_no_retry_after_a_500_that_came_late() -> None:
    clock = Clock()

    async def late(request: httpx.Request) -> httpx.Response:
        clock.now += 4.5  # 8 s of deadline, 3.5 left: under RETRY_LEFT_S
        return httpx.Response(500)

    wire = Wire(late, answering())
    error = _failure(adapter(wire, clock=clock))
    assert (error.failure, error.status, len(wire.requests)) == ("http_error", 500, 1)


def test_a_search_not_recorded_is_its_own_failure() -> None:
    async def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={NOT_RECORDED_HEADER: "1"})

    wire = Wire(missing, answering())
    error = _failure(adapter(wire))
    assert (error.failure, error.lasting, len(wire.requests)) == ("not_recorded", False, 1)


def test_the_deadline_is_held() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)  # pragma: no cover - cut by the deadline first

    started = time.monotonic()
    error = _failure(adapter(Wire(slow), deadline_s=0.2))
    assert error.failure == "timeout" and error.__context__ is None
    assert time.monotonic() - started < 3


def test_a_rejected_key_holds_every_call_off_with_no_request() -> None:
    clock = Clock()
    wire = Wire(answering(401), answering())
    source = adapter(wire, clock=clock)

    async def scene() -> list[str]:
        seen: list[str] = []
        for advance in (0.0, 10.0, HOLD_OFF_S - 20.0, 11.0):
            clock.now += advance
            try:
                seen.append((await source.day(query())).status)
            except FlightDataUnavailableError as error:
                seen.append(error.failure)
        await source.aclose()
        return seen

    assert asyncio.run(scene()) == ["rejected_key", "rejected_key", "rejected_key", "ok"]
    assert len(wire.requests) == 2


def test_the_key_is_in_no_log_line_error_detail_or_chain(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level("DEBUG")
    _day(adapter(Wire(answering())))
    for first in (answering(500, value=f"bad key {KEY}"), _raising(httpx.ReadTimeout)):
        error = _failure(adapter(Wire(first)))
        surfaces = shown(error, caplog=caplog, capsys=capsys)
        assert holding(KEY, surfaces) == []
        assert holding("serpapi.com", surfaces) == []
        assert set(error.details) == {"step", "failure", "status", "lasting"}
    assert any(r.getMessage() == "flight_data_day" for r in caplog.records)


def test_a_cancellation_propagates() -> None:
    async def never(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        raise AssertionError  # pragma: no cover

    source = adapter(Wire(never))

    async def scene() -> None:
        task = asyncio.create_task(source.day(query()))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await source.aclose()

    asyncio.run(scene())


def test_a_closed_adapter_sends_nothing() -> None:
    wire = Wire(answering())
    source = adapter(wire)
    asyncio.run(source.aclose())
    assert _failure(source).failure == "closed"
    assert wire.requests == []


def test_a_span_is_cut_to_span_days_and_the_rest_left_to_the_tools() -> None:
    wire = Wire(answering())
    source = adapter(wire, span_days=3)
    q = SpanQuery(
        origin=query().origin, destination=query().destination, first=DAY, last=DAY + timedelta(6)
    )

    async def scene() -> DayFares:
        try:
            return await source.days(q)
        finally:
            await source.aclose()

    fares = asyncio.run(scene())
    assert fares.query == q
    assert fares.checked_last == DAY + timedelta(2)
    assert [d.lowest.amount for d in fares.days if d.lowest] == [899, 899, 899]
    calendar, *days = wire.requests  # the day's body holds no calendar prices: day by day
    assert calendar.url.params["engine"] == "google_flights_calendar"
    assert sorted(r.url.params["outbound_date"] for r in days) == [
        "2026-11-19",
        "2026-11-20",
        "2026-11-21",
    ]


def test_nearest_is_never_searched_and_the_last_day_is_330_days_on() -> None:
    source = adapter(Wire(answering()))
    today = date(2026, 11, 18)
    assert asyncio.run(source.nearest(query(), today)) == ()
    assert source.last_day(today) == today + timedelta(LAST_DAY_DAYS)
    assert (source.name, source.span_days) == ("serpapi", 14)
    asyncio.run(source.aclose())
    assert content({}) == b"{}"
