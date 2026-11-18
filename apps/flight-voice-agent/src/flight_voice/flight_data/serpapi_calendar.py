"""SerpApi's Google Flights fare calendar read into a span's lowest price a day (pure, no IO):
`read_calendar`.

The calendar (`engine=google_flights_calendar`) answers `prices[]`, one `{outbound_date, price,
low_price?}` a day, and counts no flights, so each day it prices has its price as the day's
lowest and `flights` None. A day of the span it does not price is read by where it falls: inside
the run of days it priced (between its first and its last), Google listed the days around it and
not that one, so it has no flight known (`lowest` None, `known` True); before or after that run
the calendar did not cover it, so it is not checked (`known` False), never no flights.

No prices at all (SerpApi's "Google Flights Calendar hasn't returned any results", as RUH-LHR
answered on 2026-11-18, whether its status says Success or Error) is `fares` None: the adapter
then reads the span day by day. A body that is not JSON or not the answer's shape, whose
currency is not SAR, or whose prices none could be read, is `bad_answer`; any other
`search_metadata.status` "Error" is `http_error`. A price entry that is not a day of the span
with a whole-number price is dropped (logged, by reason alone).
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from t2_agentic_voice import get_logger

from flight_voice.flight_data.model import Money
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFare, DayFares, SpanQuery

__all__ = ["CalendarRead", "read_calendar"]

log = get_logger(__name__)

_NO_RESULTS: Final = "hasn't returned any results"


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)


class _Metadata(_Raw):
    status: str | None = None
    total_time_taken: float | None = None


class _Parameters(_Raw):
    currency: str | None = None


class _Body(_Raw):
    search_metadata: _Metadata = Field(default_factory=_Metadata)
    search_parameters: _Parameters = Field(default_factory=_Parameters)
    prices: list[JsonValue] = []
    error: str | None = None


class _Price(_Raw):
    outbound_date: date
    price: JsonValue = None


class CalendarRead(BaseModel):
    """What one calendar answer held: the span's fares, or None when it priced no day, and
    SerpApi's own seconds for the search."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fares: DayFares | None
    took_s: float | None = None


def read_calendar(content: bytes, q: SpanQuery) -> CalendarRead:
    """The fares of `content`, SerpApi's calendar answer to `q` (the module's docstring);
    FlightDataUnavailableError when it cannot be read or says it failed."""
    try:
        body = _Body.model_validate_json(content)
    except ValidationError:
        body = None
    if body is None:  # raised here, outside the handler: no chain to the body
        raise FlightDataUnavailableError("days", "bad_answer")
    took = body.search_metadata.total_time_taken
    nothing = _NO_RESULTS in (body.error or "")
    if body.search_metadata.status == "Error" and not nothing:
        raise FlightDataUnavailableError("days", "http_error")
    if not body.prices:
        return CalendarRead(fares=None, took_s=took)
    if body.search_parameters.currency != "SAR":
        raise FlightDataUnavailableError("days", "bad_answer")
    priced = _priced(body.prices, q)
    if not priced:
        raise FlightDataUnavailableError("days", "bad_answer")
    first, last = min(priced), max(priced)
    days = tuple(_fare(day, priced, first, last) for day in q.dates())
    return CalendarRead(fares=DayFares(query=q, status="ok", days=days), took_s=took)


def _fare(day: date, priced: dict[date, int], first: date, last: date) -> DayFare:
    if day in priced:
        return DayFare(day=day, lowest=Money(amount=priced[day]), flights=None)
    if first <= day <= last:
        return DayFare(day=day, flights=None)
    return DayFare(day=day, flights=None, known=False)


def _priced(raw: list[JsonValue], q: SpanQuery) -> dict[date, int]:
    """Each day of the span the calendar priced, with its price (the cheaper of two)."""
    found: dict[date, int] = {}
    for each in raw:
        try:
            entry = _Price.model_validate(each)
        except ValidationError:
            log.info("flight_data_calendar_day_dropped", reason="shape")
            continue
        price = entry.price
        if not isinstance(price, int) or isinstance(price, bool) or price < 0:
            log.info("flight_data_calendar_day_dropped", reason="no_price")
            continue
        if not q.first <= entry.outbound_date <= q.last:
            log.info("flight_data_calendar_day_dropped", reason="outside_span")
            continue
        held = found.get(entry.outbound_date)
        found[entry.outbound_date] = price if held is None else min(held, price)
    return found
