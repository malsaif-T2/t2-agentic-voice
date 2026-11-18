"""The flight data's port (flight_voice/flight_data/port.py): `trip_days` searches both legs at
once, a failed return comes back as a value beside the outbound, a failed outbound is raised
with no exception group chained, a cancellation propagates; and the error is `lasting` for a
rejected key or a rate limit, its details hold only the step, the failure and the status, and
it pickles."""

from __future__ import annotations

import asyncio
import pickle
from datetime import UTC, date, datetime

import pytest
from flight_voice.flight_data.model import Place
from flight_voice.flight_data.port import (
    FAILURES,
    Failure,
    FlightData,
    FlightDataUnavailableError,
    trip_days,
)
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery
from t2_agentic_voice import T2VoiceError

AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
RIYADH = Place(code="RUH", airports=("RUH",), city_en="Riyadh", city_ar="الرياض")
JEDDAH = Place(code="JED", airports=("JED",), city_en="Jeddah", city_ar="جدة")
OUT = OfferQuery(origin=RIYADH, destination=JEDDAH, day=date(2026, 11, 19))
BACK = OfferQuery(origin=JEDDAH, destination=RIYADH, day=date(2026, 11, 22))


class _Source:
    """A source whose answer to each query key is a `DayOffers`, an error to raise, or an event
    to wait on forever; it records the keys it started and the ones it finished."""

    name = "fake"
    span_days = 14

    def __init__(self, fails: dict[str, Failure] | None = None, hangs: str | None = None) -> None:
        self.fails = fails or {}
        self.hangs = hangs
        self.started: list[str] = []
        self.finished: list[str] = []
        self.both_started = asyncio.Event()

    def last_day(self, today: date) -> date:
        return today

    async def day(self, q: OfferQuery) -> DayOffers:
        self.started.append(q.key())
        if len(self.started) == 2:
            self.both_started.set()
        await asyncio.sleep(0)
        if q.key() == self.hangs:
            await asyncio.Event().wait()
        if q.key() in self.fails:
            raise FlightDataUnavailableError("day", self.fails[q.key()], 503)
        await self.both_started.wait()  # each leg runs while the other does
        self.finished.append(q.key())
        return DayOffers(query=q, status="no_flights", fetched_at=AT)

    async def days(self, q: SpanQuery) -> DayFares:
        raise NotImplementedError

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]:
        return ()

    async def aclose(self) -> None:
        return None


def test_a_fake_source_is_a_flight_data() -> None:
    source: FlightData = _Source()
    assert source.name == "fake"


def test_both_legs_are_searched_at_once() -> None:
    source = _Source()
    out, back = asyncio.run(trip_days(source, OUT, BACK))
    assert out.query == OUT
    assert isinstance(back, DayOffers)
    assert back.query == BACK
    assert sorted(source.finished) == sorted([OUT.key(), BACK.key()])


def test_a_one_way_trip_has_no_return() -> None:
    source = _Source()
    source.both_started.set()
    out, back = asyncio.run(trip_days(source, OUT, None))
    assert out.query == OUT
    assert back is None
    assert source.started == [OUT.key()]


def test_a_failed_return_comes_back_as_a_value_beside_the_outbound() -> None:
    source = _Source(fails={BACK.key(): "timeout"})
    out, back = asyncio.run(trip_days(source, OUT, BACK))
    assert out.status == "no_flights"
    assert isinstance(back, FlightDataUnavailableError)
    assert back.failure == "timeout"
    assert source.finished == [OUT.key()]


def test_a_failed_outbound_raises_with_no_group_chained() -> None:
    source = _Source(fails={OUT.key(): "rate_limited"})
    with pytest.raises(FlightDataUnavailableError) as raised:
        asyncio.run(trip_days(source, OUT, BACK))
    error = raised.value
    assert error.failure == "rate_limited"
    assert error.lasting
    assert error.__cause__ is None
    assert error.__suppress_context__
    assert not isinstance(error.__context__, BaseExceptionGroup)
    assert source.finished == [BACK.key()]  # the return was not cancelled


def test_a_cancellation_propagates_and_cancels_both_legs() -> None:
    source = _Source(hangs=BACK.key())

    async def barge_in() -> None:
        task = asyncio.create_task(trip_days(source, OUT, BACK))
        await source.both_started.wait()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(barge_in())
    assert BACK.key() not in source.finished


@pytest.mark.parametrize("failure", FAILURES)
def test_lasting_is_a_rejected_key_or_a_rate_limit(failure: Failure) -> None:
    error = FlightDataUnavailableError("days", failure)
    assert error.lasting == (failure in ("rejected_key", "rate_limited"))
    assert isinstance(error, T2VoiceError)
    assert error.code == "flight_data_unavailable"


def test_the_details_hold_the_step_the_failure_and_the_status_alone() -> None:
    error = FlightDataUnavailableError("day", "rejected_key", 401)
    assert error.details == {
        "step": "day",
        "failure": "rejected_key",
        "status": 401,
        "lasting": True,
    }
    assert "401" not in error.message
    assert "serpapi" not in str(error).lower()
    assert "key=" not in str(error).lower()


def test_an_unknown_failure_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown failure"):
        FlightDataUnavailableError("day", "exploded")  # type: ignore[arg-type]


def test_the_error_pickles_with_what_it_holds() -> None:
    error = FlightDataUnavailableError("nearest", "http_error", 500)
    back = pickle.loads(pickle.dumps(error))  # noqa: S301 - loads only bytes it dumped
    assert (back.step, back.failure, back.status, back.lasting) == (
        "nearest",
        "http_error",
        500,
        False,
    )
    assert back.details == error.details
    assert back.message == error.message
