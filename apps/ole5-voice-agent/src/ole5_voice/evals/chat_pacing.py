"""The pacing and the spend of runs K and S (plan 006's registration, "Cost and limits"): every
model request a run makes, the talker's and the judge's, goes through `PacedChat`, a `ChatModel`
that wraps the run's adapter, so the pacing sits in one place whoever sends.

Before each request it waits until the model's `ModelPacer` has room in the minute for one more
request and for the request's budget of tokens (`--input-budget-tokens` read, its own
`max_output_tokens` written), and refuses it at the day's limit (`DailyLimitError`) or when its
budgeted cost would take the run past `--cap-usd` (`CapReachedError`); each sets `stopped`, so a
run whose talker swallowed the error still stops. A request turned away before any event came (a
429, a timeout, a lost connection, a server error) waits for its `retry-after` (or
`RETRY_WAIT_S` when it names none) and is sent again, up to `--max-attempts` sends in all, each
counted. Every wait inside a request, for room or a retry, is summed in `waited_s`, and `ahead`
waits for a call's room before the call, so a run keeps its own waits out of a call's times. A
request whose provider reported no usage (a cancelled one, say) is counted at its budget, so the
spend is an upper bound. The prices are the command line's, in USD per million
tokens, the cached tokens at the input price.

The daily limit comes from the command line (`--rpd`), the day's requests so far from the run
history's lines of that day: the chat port's events carry no response headers, so Groq's
`x-ratelimit-*` headers are not read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from t2_agentic_voice import ProviderError, get_logger
from t2_agentic_voice.ports import ChatEvent, ChatModel, ChatRequest, Usage

from ole5_voice.evals.groq_answerer import Clock, Sleep
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.talker_data import ModelSpend

RETRY_WAIT_S: Final = 2.0  # a request turned away that names no retry-after waits this long
OUTPUT_BUDGET: Final = 1024  # a request that names no `max_output_tokens` (llm's default)
# Why a run stopped before its end: the cap, or the key's daily limit.
Stopped = Literal["cap", "daily_limit"]
log = get_logger(__name__)


class CapReachedError(Exception):
    """The next request's budgeted cost would take the run past `--cap-usd`."""


class DailyLimitError(Exception):
    """The next request would pass the key's daily limit for its model."""

    def __init__(self, model: str, used: int, limit: int) -> None:
        super().__init__(f"{model}: {used} of {limit} requests today")
        self.model, self.used, self.limit = model, used, limit


@dataclass(frozen=True)
class Price:
    """A model's price: USD per million tokens read and written."""

    input_usd: float
    output_usd: float

    def of(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_usd + output_tokens * self.output_usd) / 1e6


@dataclass(frozen=True)
class Limits:
    """A model's limits on the key: requests and tokens a minute, and requests a day."""

    rpm: int
    tpm: int
    rpd: int


class ModelPacer:
    """One model's limits held: the requests and the tokens in any minute, and the requests of
    the day, starting from `used_today`."""

    def __init__(self, limits: Limits, *, used_today: int, clock: Clock, sleep: Sleep) -> None:
        self.limits = limits
        self.today = used_today
        self._requests = MinutePacer(limits.rpm, clock, sleep)
        self._tokens = MinutePacer(limits.tpm, clock, sleep)

    async def room(self, model: str, tokens: int) -> float:
        """Return once one more request of `tokens` fits the minute, with the seconds it waited;
        DailyLimitError when it would pass the day's limit."""
        if self.today >= self.limits.rpd:
            raise DailyLimitError(model, self.today, self.limits.rpd)
        return await self.ahead(1, tokens)

    async def ahead(self, requests: int, tokens: int) -> float:
        """Return once `requests` more requests of `tokens` each fit the minute (as many as it
        holds), with the seconds it waited; nothing is counted."""
        waited = await self._requests.room_for(min(requests, self.limits.rpm))
        return waited + await self._tokens.room_for(min(requests * tokens, self.limits.tpm))

    def sent(self) -> None:
        """Count one request sent, now."""
        self._requests.count(1)
        self.today += 1

    def used(self, tokens: int) -> None:
        """Count the tokens a request used, now that they are known."""
        self._tokens.count(tokens)


@dataclass
class _Use:
    requests: int = 0
    retried: int = 0
    failed: int = 0
    unreported: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Spend:
    """What the run has spent, by model, at `prices`, and the cap no request may take it past;
    `before_usd` is what its earlier sessions spent (a resumed run's)."""

    prices: Mapping[str, Price]
    cap_usd: float
    before_usd: float = 0.0
    _uses: dict[str, _Use] = field(default_factory=dict)

    def use(self, model: str) -> _Use:
        if model not in self.prices:
            raise ValueError(f"the run has no price for the model {model}")
        return self._uses.setdefault(model, _Use())

    def session_usd(self) -> float:
        """What this session spent."""
        return sum(
            self.prices[model].of(use.input_tokens, use.output_tokens)
            for model, use in self._uses.items()
        )

    def cost_usd(self) -> float:
        """What the run spent, its earlier sessions included."""
        return self.before_usd + self.session_usd()

    def check(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """CapReachedError when a request of this budget would take the run past the cap."""
        if self.cost_usd() + self.prices[model].of(input_tokens, output_tokens) > self.cap_usd:
            raise CapReachedError

    def spent(self) -> tuple[ModelSpend, ...]:
        """This session's spend on each model it called, by name."""
        return tuple(
            ModelSpend(
                model=model,
                requests=use.requests,
                retried=use.retried,
                failed=use.failed,
                unreported=use.unreported,
                input_tokens=use.input_tokens,
                cached_tokens=use.cached_tokens,
                output_tokens=use.output_tokens,
                cost_usd=self.prices[model].of(use.input_tokens, use.output_tokens),
            )
            for model, use in sorted(self._uses.items())
        )

    def requests(self) -> int:
        return sum(use.requests for use in self._uses.values())

    def retries_and_failures(self) -> int:
        """The requests retried or failed this session, which a smoke test may have none of."""
        return sum(use.retried + use.failed for use in self._uses.values())

    def failures(self) -> int:
        """The requests that failed after every attempt this session, whoever caught the error:
        a talker that speaks its error notice instead still leaves its variant a failure."""
        return sum(use.failed for use in self._uses.values())


class PacedChat:
    """`inner` with every request paced, held under the cap and the day's limit, retried when
    turned away, and counted (the module's docstring); a `ChatModel`."""

    def __init__(
        self,
        inner: ChatModel,
        *,
        pacers: Mapping[str, ModelPacer],
        spend: Spend,
        input_budget: int,
        attempts: int,
        sleep: Sleep,
    ) -> None:
        self.name, self.data_flow = inner.name, inner.data_flow
        self._inner, self.pacers, self.spend = inner, pacers, spend
        self._input_budget, self._attempts, self._sleep = input_budget, attempts, sleep
        self.stopped: Stopped | None = None
        self.waited_s = 0.0  # the seconds its requests waited inside them, for room or a retry

    def _pacer(self, model: str) -> ModelPacer:
        pacer = self.pacers.get(model)
        if pacer is None:
            raise ValueError(f"the run has no limits for the model {model}")
        return pacer

    async def ahead(self, model: str, requests: int, output: int | None) -> None:
        """Return once `model` has room in the minute for `requests` more requests, each of
        the input budget and `output` tokens written (`OUTPUT_BUDGET` when None): a call that
        sends no more then finds room at once, and never waits for it inside its times."""
        await self._pacer(model).ahead(requests, self._input_budget + (output or OUTPUT_BUDGET))

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """`inner`'s events for `request`, paced and counted."""
        model = request.model
        pacer = self._pacer(model)
        use = self.spend.use(model)
        output = request.max_output_tokens or OUTPUT_BUDGET
        attempt = 0
        while True:
            attempt += 1
            self.waited_s += await self._admit(model, pacer, output)
            use.requests += 1
            use.retried += attempt > 1
            found = _Found()
            stream = self._inner.stream(request)
            wait: float | None = None
            try:
                async for event in stream:
                    found.events += 1
                    if isinstance(event, Usage):
                        found.usage = event
                    yield event
            except ProviderError as error:
                found.turned_away = not found.events and error.kind == "rate_limited"
                if found.events or not error.retryable or attempt >= self._attempts:
                    use.failed += 1
                    raise
                wait = RETRY_WAIT_S if error.retry_after_s is None else error.retry_after_s
                log.warning("model_request_retried", model=model, kind=error.kind, wait_s=wait)
            finally:
                closing = getattr(stream, "aclose", None)
                if closing is not None:
                    await closing()
                self._settle(pacer, use, found, output)
            if wait is None:
                return
            self.waited_s += wait
            await self._sleep(wait)

    async def _admit(self, model: str, pacer: ModelPacer, output: int) -> float:
        """The request let through, with the seconds it waited for room; refused at the day's
        limit or the cap."""
        try:
            waited = await pacer.room(model, self._input_budget + output)
            self.spend.check(model, self._input_budget, output)
        except DailyLimitError:
            self.stopped = "daily_limit"
            raise
        except CapReachedError:
            self.stopped = "cap"
            raise
        pacer.sent()
        return waited

    def _settle(self, pacer: ModelPacer, use: _Use, found: _Found, output: int) -> None:
        """Count what one send used: its usage, nothing for one a rate limit turned away, or
        its budget when its provider reported none."""
        if found.usage is not None:
            usage = found.usage
            use.input_tokens += usage.input_tokens
            use.cached_tokens += usage.cached_tokens
            use.output_tokens += usage.output_tokens
            pacer.used(usage.input_tokens + usage.output_tokens)
        elif not found.turned_away:
            use.unreported += 1
            use.input_tokens += self._input_budget
            use.output_tokens += output
            pacer.used(self._input_budget + output)

    async def aclose(self) -> None:
        await self._inner.aclose()


@dataclass
class _Found:
    events: int = 0
    usage: Usage | None = None
    turned_away: bool = False
