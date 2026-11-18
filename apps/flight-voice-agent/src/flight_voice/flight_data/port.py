"""The port the lean agent reads flights through (`FlightData`), the places it matches a
caller's words against (`Places`), the one error a source raises when it could not answer
(`FlightDataUnavailableError`), and `trip_days`, both legs of a trip searched at once.

An error never says "no flights": the tools say a search failed (`lasting`: it will not work
again soon, so the caller is not offered a retry). Its message and details hold the step, the
kind of failure and the HTTP status alone, never a key, a URL, the request's params or a body.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Final, Literal, Protocol, get_args

from pydantic import JsonValue
from t2_agentic_voice import T2VoiceError

from flight_voice.flight_data.model import IATA, Place
from flight_voice.flight_data.queries import DayFares, DayOffers, OfferQuery, SpanQuery

__all__ = [
    "FAILURES",
    "Failure",
    "FlightData",
    "FlightDataUnavailableError",
    "Places",
    "Step",
    "trip_days",
]

Step = Literal["day", "days", "nearest"]
Failure = Literal[
    "timeout",
    "connection",
    "http_error",
    "rate_limited",
    "rejected_key",
    "bad_answer",
    "not_recorded",
    "closed",
    "mode_fail",
]
FAILURES: Final[tuple[Failure, ...]] = get_args(Failure)
# The failures that hold for a while: asking again soon fails the same way.
_LASTING: Final[frozenset[Failure]] = frozenset({"rejected_key", "rate_limited"})
_MESSAGES: Final[dict[Failure, str]] = {
    "timeout": "The flight search did not answer in time.",
    "connection": "The flight search could not be reached.",
    "http_error": "The flight search failed to answer.",
    "rate_limited": "The flight search is limiting requests for now.",
    "rejected_key": "The flight search refused this line's key.",
    "bad_answer": "The flight search gave an answer that could not be read.",
    "not_recorded": "No recorded answer holds this search.",
    "closed": "The flight search is closed.",
    "mode_fail": "The flight search was set to fail.",
}


class FlightDataUnavailableError(T2VoiceError):
    """A flight source could not answer `step` (a day, a span, the nearest days), for `failure`,
    with the HTTP `status` when there was one. It means unknown, never no flights. `lasting` is
    true for a rejected key or a rate limit."""

    code = "flight_data_unavailable"

    def __init__(self, step: Step, failure: Failure, status: int | None = None) -> None:
        if failure not in FAILURES:
            raise ValueError(f"unknown failure {failure!r}; one of {FAILURES}")
        self.step: Step = step
        self.failure: Failure = failure
        self.status = status
        self.lasting = failure in _LASTING
        details: dict[str, JsonValue] = {
            "step": step,
            "failure": failure,
            "status": status,
            "lasting": self.lasting,
        }
        super().__init__(_MESSAGES[failure], details=details)

    def __reduce__(self) -> tuple[object, ...]:
        """Rebuilt through the constructor, with every attribute kept: an exception otherwise
        rebuilds from its message alone, which this constructor does not take."""
        return (type(self), (self.step, self.failure, self.status), self.__dict__)


class FlightData(Protocol):
    """A source of flights: the mock airline, recorded answers, or SerpApi.

    `name` is the source's ("mock", "recorded", "serpapi"); `span_days` the longest span it
    searches day by day. `day` answers one leg on one day, `days` the lowest price of each day
    of a span (a day it could not check is `known=False`; it raises only when no day answered),
    `nearest` the nearest days with flights (the mock's, exact; a live source gives ()),
    `last_day` the last day it sells from `today`. Each raises `FlightDataUnavailableError` when
    it could not answer; a cancellation always propagates. `aclose` releases what it holds."""

    @property
    def name(self) -> str: ...

    @property
    def span_days(self) -> int: ...

    def last_day(self, today: date) -> date: ...

    async def day(self, q: OfferQuery) -> DayOffers: ...

    async def days(self, q: SpanQuery) -> DayFares: ...

    async def nearest(self, q: OfferQuery, today: date) -> tuple[date, ...]: ...

    async def aclose(self) -> None: ...


class Places(Protocol):
    """The places a caller may name: `find` matches what they said (a city, an airport, a code,
    in either script) or gives None; `get` reads a code. `home` is Riyadh; `served` lists the
    mock's airports in its order, and is None for the real directory, which is no whitelist."""

    @property
    def home(self) -> Place: ...

    @property
    def served(self) -> tuple[IATA, ...] | None: ...

    def find(self, said: str) -> Place | None: ...

    def get(self, code: str) -> Place | None: ...


async def trip_days(
    data: FlightData, out: OfferQuery, back: OfferQuery | None
) -> tuple[DayOffers, DayOffers | FlightDataUnavailableError | None]:
    """The outbound's answer and the return's, both searched at once under one task group.

    Each leg hands back its `FlightDataUnavailableError` as a value, so one leg's failure never
    cancels the other: a failed return comes back as the error beside the outbound, and a failed
    outbound is raised (`from None`, with no exception group around it). The return is None
    when there is none. A cancellation (the caller barging in) propagates."""
    async with asyncio.TaskGroup() as group:
        outbound = group.create_task(_answer(data, out))
        inbound = group.create_task(_answer(data, back)) if back is not None else None
    went = outbound.result()
    if isinstance(went, FlightDataUnavailableError):
        raise went from None
    return went, inbound.result() if inbound is not None else None


async def _answer(data: FlightData, q: OfferQuery) -> DayOffers | FlightDataUnavailableError:
    try:
        return await data.day(q)
    except FlightDataUnavailableError as error:
        return error
