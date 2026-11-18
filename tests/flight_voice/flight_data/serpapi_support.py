"""What the SerpApi tests share: the seeded fixtures (tests/flight_voice/flight_data/fixtures/,
SerpApi's shape with the flights Google showed on 2026-11-18 and made-up tokens), the query
they answer, a made-up key, a fake monotonic clock, and an adapter over httpx's MockTransport."""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import httpx
from flight_voice.flight_data.carriers import CARRIERS
from flight_voice.flight_data.model import Money, Offer, Segment, offer_id
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.queries import DayOffers, OfferQuery
from flight_voice.flight_data.serpapi import SerpApiFlightData
from pydantic import SecretStr

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures"
ONE_WAY: Final = FIXTURES / "RUH_JED_2026-11-19_c1_a1.json"
ROUND_TRIP: Final = FIXTURES / "RUH_JED_2026-11-19_round_trip_outbound.json"
KEY: Final = "made-up-serpapi-key-zq9"
NOW: Final = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
DAY: Final = date(2026, 11, 19)
PLACES: Final = Directory()

type Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def query(day: date = DAY, *, origin: str = "RUH", destination: str = "JED") -> OfferQuery:
    start, end = PLACES.find(origin), PLACES.find(destination)
    assert start is not None and end is not None
    return OfferQuery(origin=start, destination=end, day=day)


def held(path: Path = ONE_WAY) -> dict[str, Any]:
    """A fixture's envelope."""
    found: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return found


def body(path: Path = ONE_WAY) -> dict[str, Any]:
    """A fixture's body: SerpApi's answer."""
    found: dict[str, Any] = held(path)["body"]
    return found


def content(value: object) -> bytes:
    return json.dumps(value).encode("utf-8")


class Clock:
    """A monotonic clock a test moves."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def no_pause(seconds: float) -> None:
    return None


def adapter(handler: Handler, *, clock: Clock | None = None, **settings: Any) -> SerpApiFlightData:
    """The adapter on a MockTransport running `handler`, with no pause before a retry."""
    return SerpApiFlightData(
        SecretStr(KEY),
        transport=httpx.MockTransport(handler),
        clock=clock or Clock(),
        now=lambda: NOW,
        pause=no_pause,
        **settings,
    )


def answering(status: int = 200, value: object | None = None) -> Handler:
    """A handler that answers `status` with `value` (the one-way fixture's body by default)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content(body() if value is None else value))

    return handler


def offers(q: OfferQuery, *prices: int) -> DayOffers:
    """An answer to `q` with one Saudia nonstop at each price, an hour apart from 08:00; none
    is `no_flights`."""
    found = []
    for n, price in enumerate(prices):
        departs = datetime(q.day.year, q.day.month, q.day.day, 8 + n)
        segment = Segment(
            carrier=CARRIERS["SV"],
            number=str(1000 + n),
            origin=q.origin.code,
            destination=q.destination.code,
            departs=departs,
            arrives=departs + timedelta(hours=2),
            minutes=120,
        )
        found.append(
            Offer(
                id=offer_id((segment,)),
                segments=(segment,),
                minutes=120,
                cabin=q.cabin,
                adults=q.adults,
                price=Money(amount=price),
                fetched_at=NOW,
            )
        )
    return DayOffers(
        query=q, status="ok" if found else "no_flights", offers=tuple(found), fetched_at=NOW
    )
