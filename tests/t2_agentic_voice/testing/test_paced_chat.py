"""The paced, capped chat model of a measurement run (paced_chat.py): each request paced within
the minute's requests and tokens, refused at the day's limit and at the cap, a request turned
away sent again after its retry-after, and every request counted, at its usage or its budget."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest
from t2_agentic_voice import ProviderError
from t2_agentic_voice.evals import (
    CapReachedError,
    DailyLimitError,
    Limits,
    ModelPacer,
    PacedChat,
    Price,
    Spend,
)
from t2_agentic_voice.ports import (
    ChatEvent,
    ChatMessage,
    ChatRequest,
    DataFlow,
    Done,
    TextDelta,
    Usage,
)
from t2_agentic_voice.testing.paced_chat import OUTPUT_BUDGET, RETRY_WAIT_S

from tests.t2_agentic_voice.testing.run_fakes import FakeClock

MODEL = "openai/gpt-oss-20b"
FLOW = DataFlow(provider="none", processed_in="the test", stored_in="nowhere", retention="none")
USAGE = Usage(input_tokens=1000, output_tokens=100)


class Inner:
    """A chat model whose requests each play the next of `plays`: an error raised after the
    given number of events, or none; it keeps whether each stream was closed."""

    name = "inner"
    data_flow = FLOW

    def __init__(self, plays: Sequence[tuple[int, BaseException | None]] = ()) -> None:
        self.plays = list(plays)
        self.sent = 0
        self.closed_streams = 0
        self.closed = False

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.sent += 1
        events, error = self.plays.pop(0) if self.plays else (3, None)
        return _Stream(self, events, error)

    async def aclose(self) -> None:
        self.closed = True


class _Stream:
    def __init__(self, inner: Inner, events: int, error: BaseException | None) -> None:
        self.inner, self.left, self.error = inner, events, error
        self.events: list[ChatEvent] = [TextDelta(text="hi"), USAGE, Done(finish_reason="stop")]

    def __aiter__(self) -> _Stream:
        return self

    async def __anext__(self) -> ChatEvent:
        if self.left == 0 and self.error is not None:
            raise self.error
        if self.left == 0 or not self.events:
            raise StopAsyncIteration
        self.left -= 1
        return self.events.pop(0)

    async def aclose(self) -> None:
        self.inner.closed_streams += 1


def _paced(
    inner: Inner,
    clock: FakeClock,
    *,
    rpm: int = 100,
    tpm: int = 1_000_000,
    rpd: int = 1000,
    today: int = 0,
    cap: float = 10.0,
    attempts: int = 3,
) -> PacedChat:
    pacer = ModelPacer(Limits(rpm, tpm, rpd), used_today=today, clock=clock, sleep=clock.sleep)
    return PacedChat(
        inner,
        pacers={MODEL: pacer},
        spend=Spend(prices={MODEL: Price(1.0, 2.0)}, cap_usd=cap),
        input_budget=2000,
        attempts=attempts,
        sleep=clock.sleep,
    )


def _request(model: str = MODEL, output: int | None = 200) -> ChatRequest:
    return ChatRequest(messages=(ChatMessage.user("hi"),), model=model, max_output_tokens=output)


async def _all(paced: PacedChat, request: ChatRequest | None = None) -> list[ChatEvent]:
    return [event async for event in paced.stream(request or _request())]


def test_a_request_passes_its_events_and_is_counted_at_its_usage() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock)
    events = asyncio.run(_all(paced))
    assert [type(e) for e in events] == [TextDelta, Usage, Done]
    (spent,) = paced.spend.spent()
    assert (spent.requests, spent.input_tokens, spent.output_tokens) == (1, 1000, 100)
    assert spent.cost_usd == pytest.approx((1000 * 1.0 + 100 * 2.0) / 1e6)
    assert paced.spend.cost_usd() == paced.spend.session_usd() == spent.cost_usd
    assert inner.closed_streams == 1 and paced.name == "inner" and paced.data_flow == FLOW


def test_the_requests_a_minute_are_held() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock, rpm=2)

    async def three() -> None:
        for _ in range(3):
            await _all(paced)

    asyncio.run(three())
    assert inner.sent == 3 and clock.pauses and sum(clock.pauses) >= 60.0


def test_the_tokens_a_minute_are_held_by_each_requests_budget() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock, tpm=3000)  # each request is budgeted 2000 + 200 tokens

    async def two() -> None:
        await _all(paced)
        await _all(paced)

    asyncio.run(two())
    assert sum(clock.pauses) >= 60.0


def test_room_ahead_is_waited_for_before_and_counted_nowhere_and_waits_inside_are_summed() -> None:
    """`ahead` waits until the minute holds the requests named (no more than its limit) and
    their tokens, counting nothing, so they then go at once; a request's waits inside it, for
    room and a retry's, are summed in `waited_s`."""
    inner = Inner([(3, None), (0, ProviderError("rate_limited", True, 4.0))])
    clock = FakeClock()
    paced = _paced(inner, clock, rpm=3, tpm=6600)  # three of 2000 + 200 budgeted tokens

    async def run() -> None:
        await _all(paced)  # one request and its 1100 tokens in the minute
        await paced.ahead(MODEL, 5, 200)  # room for three, the limit, and for 6600 tokens
        assert clock.pauses and sum(clock.pauses) >= 60.0 and paced.waited_s == 0.0
        pauses = len(clock.pauses)
        await _all(paced)  # room at once; turned away once, then sent again
        assert clock.pauses[pauses:] == [4.0] and paced.waited_s == 4.0

    asyncio.run(run())
    assert inner.sent == 3


def test_the_days_limit_refuses_the_next_request_and_marks_the_stop() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock, rpd=5, today=5)
    with pytest.raises(DailyLimitError) as raised:
        asyncio.run(_all(paced))
    assert (raised.value.used, raised.value.limit) == (5, 5)
    assert paced.stopped == "daily_limit" and inner.sent == 0


def test_the_cap_refuses_a_request_whose_budget_would_pass_it() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock, cap=0.002)  # the budget: 2000 * 1 + 200 * 2 = 0.0024
    with pytest.raises(CapReachedError):
        asyncio.run(_all(paced))
    assert paced.stopped == "cap" and inner.sent == 0


def test_a_request_turned_away_waits_for_its_retry_after_and_is_sent_again() -> None:
    inner = Inner([(0, ProviderError("rate_limited", True, 4.0))])
    clock = FakeClock()
    paced = _paced(inner, clock)
    asyncio.run(_all(paced))
    (spent,) = paced.spend.spent()
    assert inner.sent == 2 and 4.0 in clock.pauses
    assert (spent.requests, spent.retried, spent.unreported) == (2, 1, 0)
    assert spent.input_tokens == 1000  # the 429 is billed nothing
    assert paced.spend.retries_and_failures() == 1


def test_a_failure_with_no_retry_after_waits_a_fixed_time() -> None:
    inner, clock = Inner([(0, ProviderError("server_error", True))]), FakeClock()
    paced = _paced(inner, clock)
    asyncio.run(_all(paced))
    assert RETRY_WAIT_S in clock.pauses
    assert paced.spend.spent()[0].unreported == 1  # a server error may have been billed


def test_a_failure_after_an_event_is_raised_not_sent_again() -> None:
    inner, clock = Inner([(1, ProviderError("connection_lost", True))]), FakeClock()
    paced = _paced(inner, clock)
    with pytest.raises(ProviderError):
        asyncio.run(_all(paced))
    assert inner.sent == 1 and paced.spend.spent()[0].failed == 1


def test_a_request_refused_or_out_of_attempts_is_raised() -> None:
    refused = Inner([(0, ProviderError("rejected", False))])
    clock = FakeClock()
    with pytest.raises(ProviderError):
        asyncio.run(_all(_paced(refused, clock)))
    assert refused.sent == 1
    limited = Inner([(0, ProviderError("rate_limited", True, 1.0))] * 2)
    paced = _paced(limited, clock, attempts=2)
    with pytest.raises(ProviderError):
        asyncio.run(_all(paced))
    (spent,) = paced.spend.spent()
    assert limited.sent == 2 and spent.failed == 1 and spent.unreported == 0


def test_a_request_with_no_usage_is_counted_at_its_budget() -> None:
    inner, clock = Inner([(1, None)]), FakeClock()  # its text, then its end with no usage
    paced = _paced(inner, clock)
    asyncio.run(_all(paced, _request(output=None)))
    (spent,) = paced.spend.spent()
    assert (spent.unreported, spent.input_tokens, spent.output_tokens) == (1, 2000, OUTPUT_BUDGET)


def test_a_stream_its_reader_stops_is_closed_and_counted_at_its_budget() -> None:
    inner, clock = Inner(), FakeClock()
    paced = _paced(inner, clock)

    async def first_only() -> None:
        stream = paced.stream(_request())
        await anext(aiter(stream))
        await stream.aclose()  # type: ignore[attr-defined]

    asyncio.run(first_only())
    assert inner.closed_streams == 1 and paced.spend.spent()[0].unreported == 1


def test_a_model_the_run_has_no_limits_or_price_for_is_an_error() -> None:
    clock = FakeClock()
    with pytest.raises(ValueError, match="no limits"):
        asyncio.run(_all(_paced(Inner(), clock), _request(model="llama-3.1-8b-instant")))
    with pytest.raises(ValueError, match="no price"):
        Spend(prices={}, cap_usd=1.0).use(MODEL)


def test_closing_closes_the_adapter() -> None:
    inner = Inner()
    asyncio.run(_paced(inner, FakeClock()).aclose())
    assert inner.closed


def test_a_price_counts_tokens_read_and_written() -> None:
    assert Price(0.15, 0.60).of(1_000_000, 500_000) == pytest.approx(0.45)
