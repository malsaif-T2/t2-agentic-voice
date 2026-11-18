"""A span through SerpApi's fare calendar (serpapi_calendar.py, serpapi.py's `days`): the real
answers of 2026-11-18 (RUH-JED's 58 days priced; RUH-LHR's "hasn't returned any results") read
into a price a day with no flight count; a day the calendar does not price inside its run is no
flight, and outside it unknown; one request with the exact params; a calendar with no prices,
or none recorded, read day by day instead, cut to `span_days`; a calendar that failed raises;
and a span's answer leaves the count out rather than say 0."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from typing import Final

import httpx
import pytest
from flight_voice.flight_data.model import Money
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFare, DayFares, SpanQuery
from flight_voice.flight_data.recorded import recorded
from flight_voice.flight_data.serpapi import SerpApiFlightData, calendar_params
from flight_voice.flight_data.serpapi_calendar import read_calendar

from tests.flight_voice.flight_data.serpapi_support import (
    FIXTURES,
    KEY,
    PLACES,
    adapter,
    body,
    content,
)

JED_CAL: Final = FIXTURES / "RUH_JED_calendar_2026-11-19_2027-01-15_c1_a1.json"
LHR_CAL: Final = FIXTURES / "RUH_LHR_calendar_2026-11-19_2027-01-15_c1_a1.json"
FIRST: Final = date(2026, 11, 19)
LAST: Final = date(2027, 1, 15)


def span(destination: str = "JED", first: date = FIRST, last: date = LAST) -> SpanQuery:
    start, end = PLACES.find("RUH"), PLACES.find(destination)
    assert start is not None and end is not None
    return SpanQuery(origin=start, destination=end, first=first, last=last)


def _fares(source: SerpApiFlightData, q: SpanQuery) -> DayFares:
    async def one() -> DayFares:
        try:
            return await source.days(q)
        finally:
            await source.aclose()

    return asyncio.run(one())


def test_the_fixtures_hold_the_params_the_adapter_sends() -> None:
    for path, where in ((JED_CAL, "JED"), (LHR_CAL, "LHR")):
        held = json.loads(path.read_text(encoding="utf-8"))
        assert held["params"] == calendar_params(span(where))
        assert KEY not in path.read_text(encoding="utf-8")


def test_the_real_calendar_prices_every_day_and_counts_no_flights() -> None:
    read = read_calendar(content(body(JED_CAL)), span())
    assert read.fares is not None and read.took_s == 2.13
    days = read.fares.days
    assert len(days) == 58 and all(d.known and d.flights is None for d in days)
    assert days[0] == DayFare(day=FIRST, lowest=Money(amount=979), flights=None)
    assert days[3].lowest == Money(amount=369) and days[-1].lowest == Money(amount=249)
    assert read.fares.status == "ok" and read.fares.checked_last is None


def test_a_day_not_priced_is_no_flight_inside_the_run_and_unknown_outside() -> None:
    prices = [
        {"outbound_date": "2026-11-20", "price": 500},
        {"outbound_date": "2026-11-22", "price": 450, "low_price": True},
    ]
    q = span(first=FIRST, last=FIRST + timedelta(days=4))
    answer = {**body(JED_CAL), "prices": prices}
    fares = read_calendar(content(answer), q).fares
    assert fares is not None
    by_day = {d.day: d for d in fares.days}
    assert not by_day[FIRST].known  # before the run: not covered
    assert by_day[FIRST + timedelta(days=2)] == DayFare(day=FIRST + timedelta(days=2), flights=None)
    assert not by_day[FIRST + timedelta(days=4)].known  # after the run
    assert by_day[FIRST + timedelta(days=3)].lowest == Money(amount=450)


def test_no_results_is_no_calendar_and_a_failure_or_a_bad_answer_raises() -> None:
    assert read_calendar(content(body(LHR_CAL)), span("LHR")).fares is None
    failed = {**body(LHR_CAL), "search_metadata": {"status": "Error"}}
    assert read_calendar(content(failed), span("LHR")).fares is None  # its error: no results
    other = {"search_metadata": {"status": "Error"}, "error": "Something else."}
    with pytest.raises(FlightDataUnavailableError) as error:
        read_calendar(content(other), span())
    assert error.value.failure == "http_error" and error.value.step == "days"
    euros = {**body(JED_CAL), "search_parameters": {"currency": "EUR"}}
    unreadable = {**body(JED_CAL), "prices": [{"outbound_date": "2026-11-20"}]}
    for bad in (euros, unreadable):
        with pytest.raises(FlightDataUnavailableError) as error:
            read_calendar(content(bad), span())
        assert error.value.failure == "bad_answer"
    with pytest.raises(FlightDataUnavailableError):
        read_calendar(b"not json", span())


def test_a_span_is_one_calendar_request_with_the_exact_params() -> None:
    sent: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=content(body(JED_CAL)))

    fares = _fares(adapter(handler), span())
    (request,) = sent
    params = dict(request.url.params)
    assert params.pop("api_key") == KEY and params == calendar_params(span())
    assert params["engine"] == "google_flights_calendar" and params["type"] == "2"
    assert (params["date_range_start"], params["date_range_end"]) == ("2026-11-19", "2027-01-15")
    assert (params["currency"], params["gl"], params["hl"]) == ("SAR", "sa", "en")
    assert len(fares.days) == 58 and fares.query == span()


def test_a_calendar_with_no_prices_is_read_day_by_day_cut_to_span_days() -> None:
    engines: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        engine = request.url.params["engine"]
        engines.append(engine)
        if engine == "google_flights_calendar":
            return httpx.Response(200, content=content(body(LHR_CAL)))
        return httpx.Response(200, content=content(body()))

    fares = _fares(adapter(handler, span_days=3), span("LHR", last=FIRST + timedelta(days=9)))
    assert engines == ["google_flights_calendar", *["google_flights"] * 3]
    assert len(fares.days) == 3 and fares.checked_last == FIRST + timedelta(days=2)
    assert all(d.flights == 11 for d in fares.days)  # a day's search counts its flights


def test_a_calendar_that_failed_raises_and_is_not_read_day_by_day() -> None:
    engines: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        engines.append(request.url.params["engine"])
        return httpx.Response(429)

    with pytest.raises(FlightDataUnavailableError) as error:
        _fares(adapter(handler), span())
    assert (error.value.step, error.value.failure, error.value.lasting) == (
        "days",
        "rate_limited",
        True,
    )
    assert engines == ["google_flights_calendar"]


def test_a_replay_with_no_calendar_recorded_reads_the_days_it_holds() -> None:
    replay = recorded(FIXTURES, span_days=2)
    fares = _fares(replay, span(first=date(2026, 11, 26), last=date(2026, 11, 27)))
    assert fares.days[0].lowest == Money(amount=429) and fares.days[0].flights == 22
    assert not fares.days[1].known  # not recorded: unknown, never no flights
    held = recorded(FIXTURES)
    assert len(_fares(held, span()).days) == 58  # the calendar recorded for its range
