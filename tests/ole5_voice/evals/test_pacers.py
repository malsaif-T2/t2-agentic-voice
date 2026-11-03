"""The pacers of a timing run (pacers.py): at most `limit` requests counted in any minute, room
waited for between variants, each request counted when its variant ended."""

from __future__ import annotations

import asyncio

import pytest
from ole5_voice.evals.pacers import WINDOW_S, MinutePacer

from tests.ole5_voice.evals.run_support import FakeClock


def most_in_a_minute(times: list[float]) -> int:
    """The most of `times` that fall in any window of `WINDOW_S` seconds."""
    return max(
        (sum(1 for t in times if start <= t < start + WINDOW_S) for start in times), default=0
    )


@pytest.mark.parametrize(("limit", "each"), [(10, 2), (5, 2), (5, 1), (10, 3)])
def test_a_pacer_holds_its_limit_in_any_minute(limit: int, each: int) -> None:
    """Variants that each send `each` requests, counted as they end 5 s after they start."""
    clock = FakeClock()
    pacer = MinutePacer(limit, clock, clock.sleep)
    sent: list[float] = []

    async def run() -> None:
        for _ in range(40):
            await pacer.room_for(each)
            sent.extend([clock.now] * each)  # sent as the variant starts, at the earliest
            clock.now += 5.0
            pacer.count(each)

    asyncio.run(run())
    assert most_in_a_minute(sent) <= limit
    assert clock.pauses  # it waited
    assert len(sent) == 40 * each


def test_a_pacer_waits_only_as_long_as_the_oldest_request_needs_to_leave() -> None:
    clock = FakeClock()
    pacer = MinutePacer(5, clock, clock.sleep)
    pacer.count(5)
    clock.now += 10.0
    asyncio.run(pacer.room_for(2))
    assert clock.pauses == [pytest.approx(50.001)]
    assert pacer.in_window() == 0
    asyncio.run(pacer.room_for(5))
    assert len(clock.pauses) == 1  # room at once


def test_more_than_the_limit_never_fits_and_a_limit_is_at_least_one() -> None:
    clock = FakeClock()
    with pytest.raises(ValueError, match="never fit"):
        asyncio.run(MinutePacer(5, clock, clock.sleep).room_for(6))
    with pytest.raises(ValueError, match="at least one"):
        MinutePacer(0, clock, clock.sleep)
