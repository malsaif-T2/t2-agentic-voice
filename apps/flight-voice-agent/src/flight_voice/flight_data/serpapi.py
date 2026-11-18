"""SerpApi's Google Flights engine behind the port (`SerpApiFlightData`), on one long-lived
httpx client, as Ole5's knowledge base is: a transport a test injects, closed by the app's
lifespan (`aclose`).

**One day** is one `GET /search`: a one-way search (`type=2`) between the places' airports
(comma-joined), on the day, in the cabin, for the travelers, in SAR, Saudi Google in English
(the Arabic names come from our own files), with one stop or fewer (`stops=2`), and SerpApi's
`deep_search` only when set. Never `no_cache`: SerpApi's hour-long cache is free and fast.

**The deadline.** A whole day runs under `deadline_s`; the first attempt gets the whole budget
(its read timeout is `deadline_s - 1`). There is no retry after a read timeout, since a second
slow search would miss as well; one retry, after `RETRY_PAUSE_S`, only after a quick failure (a
connect error, or a 500, 502, 503 or 504) with `RETRY_LEFT_S` of the deadline left. A 401 or 403
is a rejected key: logged once at ERROR, then every call is refused for `HOLD_OFF_S` with no
request sent. 429 is `rate_limited`; any other status is `http_error`. A cancellation is never
caught.

**What is shown.** httpx's own INFO line prints the URL, which holds the key, so its logger is
held to WARNING. A search logs `flight_data_day` (the source, the query's key, the status, the
offers, the wall seconds and SerpApi's own) and a failure `flight_data_day_failed`; neither
holds the key, the URL or a body, and every error is raised outside its handler, so no chain
leads to httpx's request.

`days` cuts a span to `span_days` (setting `checked_last`) and fans it out (fanout.py);
`nearest` gives (); `last_day` is 330 days on.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Final

import httpx
from pydantic import SecretStr
from t2_agentic_voice import get_logger

from flight_voice.flight_data.fanout import DayFn, span_of
from flight_voice.flight_data.port import Failure, FlightDataUnavailableError
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery
from flight_voice.flight_data.serpapi_parse import read_day

__all__ = [
    "BASE_URL",
    "HOLD_OFF_S",
    "LAST_DAY_DAYS",
    "NOT_RECORDED_HEADER",
    "RETRY_LEFT_S",
    "SerpApiFlightData",
    "search_params",
]

log = get_logger(__name__)

BASE_URL: Final = "https://serpapi.com"
HOLD_OFF_S: Final = 300.0
RETRY_LEFT_S: Final = 7.0
RETRY_PAUSE_S: Final = 0.25
LAST_DAY_DAYS: Final = 330
LIMITS: Final = httpx.Limits(
    max_connections=16, max_keepalive_connections=16, keepalive_expiry=300.0
)
_CLASSES: Final = {"economy": "1", "business": "3", "first": "4"}
_RETRIED: Final = frozenset({500, 502, 503, 504})
_REJECTED: Final = frozenset({401, 403})
# The header a replay (recorded.py) marks a search it holds no answer for with.
NOT_RECORDED_HEADER: Final = "x-flight-data-not-recorded"


def search_params(q: OfferQuery, *, deep_search: bool = False) -> dict[str, str]:
    """The query's parameters as the adapter sends them, the key aside."""
    params = {
        "engine": "google_flights",
        "type": "2",
        "departure_id": ",".join(q.origin.airports),
        "arrival_id": ",".join(q.destination.airports),
        "outbound_date": q.day.isoformat(),
        "travel_class": _CLASSES[q.cabin],
        "adults": str(q.adults),
        "currency": "SAR",
        "gl": "sa",
        "hl": "en",
        "stops": "2",
    }
    if deep_search:
        params["deep_search"] = "true"
    return params


class _Attempt:
    """What one request gave: a response, or a failure, its HTTP status, and whether it came
    quickly enough that a retry may help."""

    def __init__(
        self,
        response: httpx.Response | None,
        failure: Failure | None = None,
        status: int | None = None,
        *,
        quick: bool = False,
    ) -> None:
        self.response = response
        self.failure: Failure = failure or "http_error"
        self.status = status
        self.quick = quick


class SerpApiFlightData:
    """SerpApi's Google Flights as a `FlightData` source (the module's docstring), reached with
    `key`. `clock` (monotonic seconds) times the hold-off and the retry's budget, `now` stamps
    each answer, and `transport` stands in for the network in a test."""

    def __init__(
        self,
        key: SecretStr,
        *,
        deadline_s: float = 13.0,
        span_days: int = 14,
        span_concurrency: int = 14,
        span_deadline_s: float = 12.0,
        deep_search: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        pause: Callable[[float], Awaitable[None]] = asyncio.sleep,
        name: str = "serpapi",
    ) -> None:
        logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO line prints the URL
        self._key = key
        self._deadline_s = deadline_s
        self._span_days = span_days
        self._concurrency = span_concurrency
        self._span_deadline_s = span_deadline_s
        self._deep = deep_search
        self._clock = clock
        self._now = now
        self._pause = pause
        self._name = name
        self._held_until: float | None = None
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            transport=transport,
            timeout=httpx.Timeout(max(deadline_s - 1, 0.5), connect=3.0, pool=None),
            limits=LIMITS,
            follow_redirects=False,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def span_days(self) -> int:
        return self._span_days

    def last_day(self, today: date) -> date:
        """The last day searched: 330 days on (the airlines sell about that far ahead)."""
        return today + timedelta(days=LAST_DAY_DAYS)

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        """None looked for: each would be another paid search."""
        return ()

    async def days(self, q: SpanQuery) -> DayFares:
        """The lowest price of each day of the span, cut to `span_days`."""
        return await self.span(self.day, q)

    async def span(self, day_fn: DayFn, q: SpanQuery) -> DayFares:
        """The span read through `day_fn` (this adapter's `day`, or a cache's over it), cut to
        `span_days`, under the span's concurrency and deadline."""
        return await span_of(
            day_fn,
            q,
            span_days=self._span_days,
            concurrency=self._concurrency,
            deadline_s=self._span_deadline_s,
        )

    async def aclose(self) -> None:
        """Close the client and its kept-open connections; a search after it is `closed`."""
        await self._client.aclose()

    async def day(self, q: OfferQuery) -> DayOffers:
        """One leg on one day (the module's docstring)."""
        if self._client.is_closed:
            raise FlightDataUnavailableError("day", "closed")
        if self._held_until is not None and self._clock() < self._held_until:
            raise FlightDataUnavailableError("day", "rejected_key", 401)
        started, wall = self._clock(), time.perf_counter()
        failure: FlightDataUnavailableError | None = None
        try:
            async with asyncio.timeout(self._deadline_s):
                response = await self._answer(q, started)
                read = read_day(response.content, q, self._now())
        except FlightDataUnavailableError as error:
            failure = error
        except TimeoutError:
            failure = FlightDataUnavailableError("day", "timeout")
        if failure is not None:  # raised here, outside the handlers: no chain to a request
            log.warning(
                "flight_data_day_failed",
                source=self._name,
                query=q.key(),
                failure=failure.failure,
                status=failure.status,
            )
            raise failure
        log.info(
            "flight_data_day",
            source=self._name,
            query=q.key(),
            status=read.answer.status,
            offers=len(read.answer.offers),
            wall_s=round(time.perf_counter() - wall, 3),
            took_s=read.took_s,
        )
        return read.answer

    async def _answer(self, q: OfferQuery, started: float) -> httpx.Response:
        """The 200 answer to `q`, asked once more after a quick failure with time left."""
        params = search_params(q, deep_search=self._deep)
        params["api_key"] = self._key.get_secret_value()
        attempt = await self._get(params)
        left = self._deadline_s - (self._clock() - started)
        if attempt.response is None and attempt.quick and left >= RETRY_LEFT_S:
            log.info("flight_data_day_retried", source=self._name, failure=attempt.failure)
            await self._pause(RETRY_PAUSE_S)
            attempt = await self._get(params)
        if attempt.response is None:
            raise FlightDataUnavailableError("day", attempt.failure, attempt.status)
        return attempt.response

    async def _get(self, params: dict[str, str]) -> _Attempt:
        try:
            response = await self._client.get("/search", params=params)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return _Attempt(None, "connection", quick=True)
        except httpx.TimeoutException:
            return _Attempt(None, "timeout")
        except httpx.TransportError:
            return _Attempt(None, "connection")
        except httpx.HTTPError:
            return _Attempt(None, "http_error")
        return self._judged(response)

    def _judged(self, response: httpx.Response) -> _Attempt:
        """The attempt a status makes; a rejected key, a rate limit or a search not recorded
        raises at once, with no retry."""
        status = response.status_code
        if status == httpx.codes.OK:
            return _Attempt(response)
        if status in _REJECTED:
            self._reject(status)
            raise FlightDataUnavailableError("day", "rejected_key", status)
        if status == httpx.codes.TOO_MANY_REQUESTS:
            raise FlightDataUnavailableError("day", "rate_limited", status)
        if status == httpx.codes.NOT_FOUND and NOT_RECORDED_HEADER in response.headers:
            raise FlightDataUnavailableError("day", "not_recorded", status)
        return _Attempt(None, "http_error", status, quick=status in _RETRIED)

    def _reject(self, status: int) -> None:
        """Hold every call off for `HOLD_OFF_S`; logged once per hold."""
        held = self._held_until is not None and self._clock() < self._held_until
        self._held_until = self._clock() + HOLD_OFF_S
        if not held:
            log.error("flight_data_key_rejected", source=self._name, status=status)
