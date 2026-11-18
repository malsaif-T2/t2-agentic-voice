"""A flight source that keeps what it answered: `Logged(inner)` passes every call through to
`inner` and keeps each day's answer in `answers`, in order, so run F reads its facts from what
the call was told, never from the mock worked out again."""

from __future__ import annotations

from datetime import date

from flight_voice.flight_data.port import FlightData
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery

__all__ = ["Logged"]


class Logged:
    """`inner`, each day it answered kept in `answers`."""

    def __init__(self, inner: FlightData) -> None:
        self.inner = inner
        self.answers: list[DayOffers] = []

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def span_days(self) -> int:
        return self.inner.span_days

    def last_day(self, today: date) -> date:
        return self.inner.last_day(today)

    async def day(self, q: OfferQuery) -> DayOffers:
        answer = await self.inner.day(q)
        self.answers.append(answer)
        return answer

    async def days(self, q: SpanQuery) -> DayFares:
        return await self.inner.days(q)

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        return await self.inner.nearest(q, today)

    async def aclose(self) -> None:
        await self.inner.aclose()
