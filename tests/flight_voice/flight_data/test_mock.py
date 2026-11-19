"""The mock airline behind the port (flight_voice/flight_data/mock.py, logged.py): its offers
carry the carrier's ids (`T2401-…`), the fare times the travelers and the exact seats; a route
it does not fly and a cabin it does not sell are refused on a day and on a span alike before
any mode applies; its fail mode raises `mode_fail`; a slow round trip waits about one slow read;
a span is the fare calendar times the travelers; `nearest` and `last_day` are the scripted
search's; its places match as `find_airport` does; and `Logged` keeps what was answered."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

import pytest
from flight_voice.airline.airports import AIRPORTS, NAMES, find_airport
from flight_voice.airline.fares import calendar, fare, seats_left
from flight_voice.airline.schedule import departures, window
from flight_voice.airline.system import Airline
from flight_voice.flight_data.logged import Logged
from flight_voice.flight_data.mock import MockFlightData, MockPlaces, place_of
from flight_voice.flight_data.model import Carrier, Place
from flight_voice.flight_data.port import FlightDataUnavailableError, trip_days
from flight_voice.flight_data.queries import OfferQuery, SpanQuery
from flight_voice.tools.search import nearest_days

from tests.flight_voice.scenario_dates import TODAY

T2 = Carrier(code="T2", name_en="T2 Air", name_ar="طيران تي تو")
AT = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 19)
PLACES = MockPlaces()


def _data(**modes: Any) -> MockFlightData:
    return MockFlightData(Airline(today=lambda: TODAY, **modes), T2, clock=lambda: AT)


def _q(origin: str, destination: str, day: date = DAY, **more: Any) -> OfferQuery:
    start, end = PLACES.get(origin), PLACES.get(destination)
    assert start is not None and end is not None
    return OfferQuery(origin=start, destination=end, day=day, **more)


def _span(origin: str, destination: str, first: date, last: date, **more: Any) -> SpanQuery:
    q = _q(origin, destination)
    return SpanQuery(origin=q.origin, destination=q.destination, first=first, last=last, **more)


def test_a_day_gives_each_flight_as_an_offer_with_its_fare_times_the_travelers() -> None:
    answer = asyncio.run(_data().day(_q("RUH", "JED", adults=2, cabin="business")))
    flown = departures("RUH", "JED", DAY)
    assert answer.status == "ok" and answer.fetched_at == AT
    assert [o.id for o in answer.offers] == [f"T2{d.flight.number}-2026-11-19" for d in flown]
    for o, d in zip(answer.offers, flown, strict=True):
        assert o.price.amount == 2 * (fare(d, "business") or 0) and o.adults == 2
        assert o.seats_left == seats_left(d.flight, DAY, "business")
        assert o.departs.strftime("%H:%M") == d.departs_at.strftime("%H:%M")
        assert o.departs.tzinfo is None and o.flights == (f"T2 {d.flight.number}",)
        assert o.segments[0].aircraft == d.flight.aircraft and o.nonstop


def test_a_route_not_flown_and_a_cabin_not_sold_are_refused_before_any_mode() -> None:
    data = _data(search_mode="fail")
    for answer in (
        asyncio.run(data.day(_q("JED", "DXB"))),
        asyncio.run(data.days(_span("JED", "DXB", DAY, DAY))),
    ):
        assert answer.status == "not_served" and answer.served == tuple(AIRPORTS)
    for answer in (
        asyncio.run(data.day(_q("RUH", "JED", cabin="first"))),
        asyncio.run(data.days(_span("RUH", "JED", DAY, DAY, cabin="first"))),
    ):
        assert answer.status == "cabin_not_sold" and answer.cabins == ("economy", "business")
    bare = OfferQuery(origin=place_of(AIRPORTS["RUH"]), destination=Place.bare("ELQ"), day=DAY)
    assert asyncio.run(data.day(bare)).status == "not_served"


def test_the_fail_mode_raises_mode_fail_and_a_day_with_no_flight_is_no_flights() -> None:
    with pytest.raises(FlightDataUnavailableError) as raised:
        asyncio.run(_data(search_mode="fail").day(_q("RUH", "JED")))
    assert (raised.value.step, raised.value.failure) == ("day", "mode_fail")
    with pytest.raises(FlightDataUnavailableError):
        asyncio.run(_data(search_mode="fail").days(_span("RUH", "JED", DAY, DAY)))
    tuesday = asyncio.run(_data().day(_q("RUH", "SIN", date(2026, 11, 17))))
    assert tuesday.status == "no_flights" and tuesday.offers == ()


def test_a_slow_round_trip_waits_about_one_slow_read() -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        await asyncio.sleep(0)

    airline = Airline(today=lambda: TODAY, search_mode="slow", slow_s=4.0, sleep=sleep)
    data = MockFlightData(airline, T2)
    out, back = asyncio.run(trip_days(data, _q("RUH", "JED"), _q("JED", "RUH", date(2026, 11, 21))))
    assert out.status == "ok" and back is not None and not isinstance(back, Exception)
    assert slept == [4.0, 4.0]  # one each, at the same time


def test_a_span_is_the_fare_calendar_times_the_travelers() -> None:
    first, last = date(2026, 11, 16), date(2026, 11, 22)
    answer = asyncio.run(_data().days(_span("RUH", "SIN", first, last, adults=3)))
    mock = calendar("RUH", "SIN", first, last, "economy")
    assert [d.day for d in answer.days] == [d.day for d in mock]
    for got, want in zip(answer.days, mock, strict=True):
        assert (got.lowest.amount if got.lowest else None) == (
            None if want.fare is None else 3 * want.fare
        )
        assert got.flights == len(departures("RUH", "SIN", want.day)) and got.known
    assert answer.times is not None and all(":" in t for t in answer.times)


def test_nearest_and_last_day_are_the_scripted_searchs() -> None:
    data = _data()
    tuesday = date(2026, 11, 17)
    near = asyncio.run(data.nearest(_q("RUH", "SIN", tuesday), TODAY))
    start, end = AIRPORTS["RUH"], AIRPORTS["SIN"]
    assert list(near) == nearest_days(start, end, tuesday, TODAY)
    assert data.last_day(TODAY) == window(TODAY)[1]
    assert asyncio.run(data.nearest(_q("JED", "DXB"), TODAY)) == ()


def test_the_mock_places_match_as_find_airport_does() -> None:
    for name in NAMES:
        found, airport = PLACES.find(name), find_airport(name)
        assert airport is not None and found is not None and found.code == airport.code
    assert PLACES.find("Qassim") is None and PLACES.get("ELQ") is None
    assert PLACES.home.code == "RUH" and PLACES.served == tuple(AIRPORTS)


def test_logged_keeps_each_day_it_answered() -> None:
    logged = Logged(_data())
    asyncio.run(logged.day(_q("RUH", "JED")))
    asyncio.run(logged.days(_span("RUH", "JED", DAY, DAY)))
    assert [a.query.key() for a in logged.answers] == ["RUH-JED-2026-11-19-economy-1"]
    assert logged.name == "mock" and logged.span_days == 62


def test_a_span_asked_each_day_gives_each_days_offers_from_the_timetable() -> None:
    first, last = date(2026, 11, 16), date(2026, 11, 22)
    data = _data()
    answer = asyncio.run(data.days(_span("RUH", "SIN", first, last, adults=2, each_day=True)))
    for each in answer.days:
        day = asyncio.run(data.day(_q("RUH", "SIN", each.day, adults=2)))
        assert each.offers == day.offers and each.flights == len(day.offers)
    assert asyncio.run(data.days(_span("RUH", "SIN", first, last))).days[0].offers is None
