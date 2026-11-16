"""The paced, capped chat model of a measurement run that spends: every model request a run
makes, its talker's and its judge's, goes through `PacedChat`, a `ChatModel` that wraps the run's
adapter, so the pacing sits in one place whoever sends.

Before each request it waits until the model's `ModelPacer` has room in the minute for one more
request and for the request's budget of tokens (the run's input budget read, the request's own
`max_output_tokens` written), and refuses it at the day's limit (`DailyLimitError`) or when its
budgeted cost would take the run past its cap (`CapReachedError`); each sets `stopped`, so a
run whose talker swallowed the error still stops. A request turned away before any event came (a
429, a timeout, a lost connection, a server error) waits for its `retry-after` (or
`RETRY_WAIT_S` when it names none) and is sent again, up to `attempts` sends in all, each
counted. Every wait inside a request, for room or a retry, is summed in `waited_s`, and `ahead`
waits for a call's room before the call, so a run keeps its own waits out of a call's times. A
request whose provider reported no usage (a cancelled one, say) is counted at its budget, so the
spend is an upper bound.

The daily limit is the run's to give (`Limits.rpd`), and the day's requests so far come from the
run histories (`requests_today`): the chat port's events carry no response headers, so a
provider's `x-ratelimit-*` headers are not read. Public through the `evals` facade.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatModel, ChatRequest, Usage
from t2_agentic_voice.testing.run_pacing import DailyLimitError, ModelPacer, RunSleep
from t2_agentic_voice.testing.run_spend import CapReachedError, ModelUse, Spend

RETRY_WAIT_S: Final = 2.0  # a request turned away that names no retry-after waits this long
OUTPUT_BUDGET: Final = 1024  # a request that names no `max_output_tokens`
# Why a run stopped before its end: the cap, or the key's daily limit.
Stopped = Literal["cap", "daily_limit"]
log = get_logger(__name__)


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
        sleep: RunSleep,
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

    def _settle(self, pacer: ModelPacer, use: ModelUse, found: _Found, output: int) -> None:
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
