"""What the lean agent asks a flight source, and what the source answers: one day's offers on a
route (`OfferQuery`, `DayOffers`), or the lowest price of each day of a span (`SpanQuery`,
`DayFares`).

An answer's `status` says what the source found: `ok` (offers, in departure order),
`no_flights` (it answered and has none that day), `not_served` or `cabin_not_sold` (the mock
alone, with what it serves or sells). A source that could not answer raises
`FlightDataUnavailableError` (port.py) instead, so a failure is never read as no flights. In a
span, a day that could not be checked is `known=False`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flight_voice.flight_data.model import IATA, Cabin, Money, Offer, Place, aware_utc

__all__ = ["DayFare", "DayFares", "DayOffers", "DayStatus", "OfferQuery", "SpanQuery"]

DayStatus = Literal["ok", "no_flights", "not_served", "cabin_not_sold"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _place_key(place: Place) -> str:
    return "+".join(place.airports)


class OfferQuery(_Frozen):
    """One leg on one day: from where, to where, the cabin and the travelers."""

    origin: Place
    destination: Place
    day: date
    cabin: Cabin = "economy"
    adults: int = Field(default=1, ge=1, le=9)

    def key(self) -> str:
        """The query as one string, for a cache and the logs: "RUH-JED-2026-11-19-economy-1"; a
        place of several airports joins them with "+" ("RUH-LHR+LGW+STN-...")."""
        return "-".join(
            (
                _place_key(self.origin),
                _place_key(self.destination),
                self.day.isoformat(),
                self.cabin,
                str(self.adults),
            )
        )


class SpanQuery(_Frozen):
    """One leg on each day from `first` to `last`, both included."""

    origin: Place
    destination: Place
    first: date
    last: date
    cabin: Cabin = "economy"
    adults: int = Field(default=1, ge=1, le=9)

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.last < self.first:
            raise ValueError("a span's last day is not before its first")
        return self

    def day(self, on: date) -> OfferQuery:
        """The same leg on the one day `on`."""
        return OfferQuery(
            origin=self.origin,
            destination=self.destination,
            day=on,
            cabin=self.cabin,
            adults=self.adults,
        )

    def dates(self) -> tuple[date, ...]:
        """Every day of the span, in order."""
        count = (self.last - self.first).days + 1
        return tuple(self.first + timedelta(days=i) for i in range(count))


class DayOffers(_Frozen):
    """A source's answer for one `OfferQuery`. `offers` is in departure order and non-empty
    only when `status` is `ok`; `cabins` (on `cabin_not_sold`) and `served` (on `not_served`)
    come from the mock; `cities` are the provider's names of the airports it answered with, for
    a bare place."""

    query: OfferQuery
    status: DayStatus
    offers: tuple[Offer, ...] = ()
    cabins: tuple[Cabin, ...] | None = None
    served: tuple[IATA, ...] | None = None
    cities: tuple[tuple[IATA, str], ...] = ()
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return aware_utc(value)

    @model_validator(mode="after")
    def _offers_only_when_ok(self) -> Self:
        if self.offers and self.status != "ok":
            raise ValueError("an answer holds offers only when its status is ok")
        return self


class DayFare(_Frozen):
    """One day of a span: its lowest price and how many flights it has, or `known=False` when
    that day could not be checked. `lowest` is None on a day with no flights."""

    day: date
    lowest: Money | None = None
    flights: int = Field(default=0, ge=0)
    known: bool = True


class DayFares(_Frozen):
    """A source's answer for one `SpanQuery`: each day checked, in order. `served` and `cabins`
    come from the mock on `not_served` and `cabin_not_sold`; `times` are the route's fixed daily
    times (the mock alone); `checked_last` is set when the span was cut to the source's
    `span_days`."""

    query: SpanQuery
    status: DayStatus
    days: tuple[DayFare, ...] = ()
    served: tuple[IATA, ...] | None = None
    cabins: tuple[Cabin, ...] | None = None
    times: tuple[str, ...] | None = None
    checked_last: date | None = None
