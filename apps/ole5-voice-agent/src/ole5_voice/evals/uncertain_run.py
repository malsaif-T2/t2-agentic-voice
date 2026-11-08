"""The asking part of a `poe uncertain` run (`uncertain.py`; plan 006's registration, U): for each
overlap, one short chat completion through the library's chat model port, which reads the reply
the caller heard and the words said over it and answers with one word, `stop` or `go_on`.

**The request** (`request_of`) is the one a call ships (the `evals` facade's
`uncertain_overlap_request`, D-069): an instruction written for the pattern, never for an item,
the reply and the words as data, the model's settings from the run's `llm` group (its reasoning
effort sent as the settings give it, the adapter leaving it out for a model that takes none) and
the run's temperature. **The answer** is the facade's `uncertain_overlap_answer`: the stream's
text in lower case with everything but its letters dropped: `stop`, `goon` (go on) or else
`unclear`.

**Limits** (`Asking`): one request at a time, paced at `--rpm` a minute (pacers.py); before each,
the run stops at `--day-requests`, the requests the key may still send today (the port reads no
rate-limit header, so the owner gives it from Groq's console), and at `--cap-usd`, each request
charged its budget, the most it can cost (`Prices.budget`), until its usage gives what it did
cost. A request turned away as rate-limited waits its `retry-after` (or `RATE_LIMIT_PAUSE_S`)
and is asked again, up to `--max-attempts` in all, then stops the run (`RateLimitedError`);
another failure that may pass waits `RETRY_PAUSE_S`; after the last attempt, or a refusal no
retry mends, the overlap is a failure, counted apart. A request still running at
`--item-timeout-s` is `stuck`. Every time is on the wall clock (`time.perf_counter`).

**The run** (`asked`): the smoke test, the first overlap, asked once and never scored, which
must answer one of the two words on its first attempt; then each overlap, its result written as
it finishes (`RESULTS_FILE`) with a progress line of identifiers and verdicts, never the words.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from t2_agentic_voice import ProviderError, VoiceSettings, get_logger
from t2_agentic_voice.evals import uncertain_overlap_answer, uncertain_overlap_request
from t2_agentic_voice.ports import ChatModel, ChatRequest, TextDelta, Usage

from ole5_voice.evals.groq_answerer import Clock, Sleep
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.uncertain_score import (
    ArmAnswer,
    UncertainOverlap,
    UncertainResult,
    judged,
)

RESULTS_FILE: Final = "results.jsonl"  # each overlap's result, as it finishes
RATE_LIMIT_PAUSE_S: Final = 60.0  # a whole pacer window, when no retry-after came
RETRY_PAUSE_S: Final = 3.0  # after another failure that may pass (groq_answerer.py's)
# The tokens a request's messages may take beyond their bytes: each message's role and markers.
_OVERHEAD_TOKENS: Final = 32
# Why a run stopped before its last overlap: its smoke test failed, its cap, the requests the
# key may send today, a request still rate-limited on its last attempt, or an interrupt.
Stopped = Literal["smoke_failed", "cap", "day_limit", "rate_limited", "interrupted"]
log = get_logger(__name__)


def request_of(
    overlap: UncertainOverlap, settings: VoiceSettings, temperature: float
) -> ChatRequest:
    """The one request that asks the model about `overlap`."""
    llm = settings.llm
    return uncertain_overlap_request(
        overlap.reply,
        overlap.words,
        model=llm.model,
        reasoning_effort=llm.reasoning_effort,
        max_output_tokens=llm.max_output_tokens,
        temperature=temperature,
    )


@dataclass(frozen=True)
class Prices:
    """USD per million tokens: those read, those of them cached, and those written."""

    input_usd: float
    cached_usd: float
    output_usd: float

    def cost(self, usage: Usage) -> float:
        fresh = usage.input_tokens - usage.cached_tokens
        read = fresh * self.input_usd + usage.cached_tokens * self.cached_usd
        return (read + usage.output_tokens * self.output_usd) / 1e6

    def budget(self, request: ChatRequest) -> float:
        """The most `request` can cost: a token for each byte of its messages and their
        overhead, read at the uncached price, and every token it may write."""
        read = sum(len(m.content.encode("utf-8")) for m in request.messages) + _OVERHEAD_TOKENS
        most = request.max_output_tokens or 0
        return (read * max(self.input_usd, self.cached_usd) + most * self.output_usd) / 1e6


class CapReachedError(Exception):
    """The next request's budget would take the run past `--cap-usd`."""


class DayLimitError(Exception):
    """The next request would pass `--day-requests`."""


class RateLimitedError(Exception):
    """A request was still rate-limited on its last attempt."""


@dataclass
class Asking:
    """One run's asking: the model, its pacer, prices and limits, and what it spent."""

    model: ChatModel
    pacer: MinutePacer
    prices: Prices
    cap_usd: float
    day_requests: int
    max_attempts: int
    item_timeout_s: float
    clock: Clock
    sleep: Sleep
    requests: int = 0
    spent_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    async def ask(self, request: ChatRequest) -> ArmAnswer:
        """The model's answer to `request`, asked again while it may pass (the module's
        docstring)."""
        attempt = 0
        while True:
            attempt += 1
            budget = self.prices.budget(request)
            if self.requests >= self.day_requests:
                raise DayLimitError
            if self.spent_usd + budget > self.cap_usd:
                raise CapReachedError
            await self.pacer.room_for(1)
            self.pacer.count(1)
            self.requests += 1
            try:
                return await self._answer(request, attempt, budget)
            except ProviderError as error:
                self.spent_usd += budget  # a request turned away may still be billed
                pause = RETRY_PAUSE_S
                if error.kind == "rate_limited":
                    if attempt >= self.max_attempts:
                        raise RateLimitedError from None
                    pause = error.retry_after_s or RATE_LIMIT_PAUSE_S
                elif not error.retryable or attempt >= self.max_attempts:
                    log.warning("provider_failure", kind=error.kind, attempts=attempt)
                    return ArmAnswer(failure=error.kind, attempts=attempt)
                log.warning("request_refused", kind=error.kind, attempt=attempt, pause_s=pause)
                await self.sleep(pause)
            except TimeoutError:
                self.spent_usd += budget
                log.warning("request_stuck", attempts=attempt)
                return ArmAnswer(failure="stuck", attempts=attempt)

    async def _answer(self, request: ChatRequest, attempt: int, budget: float) -> ArmAnswer:
        """One request's stream read whole, timed from its start."""
        began = self.clock()
        first: float | None = None
        parts: list[str] = []
        usage: Usage | None = None
        async with asyncio.timeout(self.item_timeout_s):
            async for event in self.model.stream(request):
                if isinstance(event, TextDelta):
                    first = self.clock() if first is None else first
                    parts.append(event.text)
                elif isinstance(event, Usage):
                    usage = event
        ended = self.clock()
        self.spent_usd += budget if usage is None else self.prices.cost(usage)
        tokens = (0, 0, 0) if usage is None else _tokens(usage)
        self.input_tokens += tokens[0]
        self.output_tokens += tokens[1]
        return ArmAnswer(
            answer=uncertain_overlap_answer("".join(parts)),
            attempts=attempt,
            first_text_ms=None if first is None else (first - began) * 1000,
            answer_ms=(ended - began) * 1000,
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            cached_tokens=tokens[2],
        )


def _tokens(usage: Usage) -> tuple[int, int, int]:
    return usage.input_tokens, usage.output_tokens, usage.cached_tokens


@dataclass
class Found:
    """What a run measured so far, and why it stopped early, if it did."""

    results: list[UncertainResult] = field(default_factory=list)
    stopped: Stopped | None = None


async def asked(
    asking: Asking,
    todo: Sequence[tuple[UncertainOverlap, ChatRequest]],
    found: Found,
    out: Path,
    smoke_only: bool,
) -> None:
    """The smoke test, then each overlap, in order, until the last, the cap, the day's limit or
    a request still rate-limited."""
    try:
        smoke = await asking.ask(todo[0][1])
        if smoke.failure or smoke.answer == "unclear" or smoke.attempts > 1:
            found.stopped = "smoke_failed"
            log.error("smoke_failed", failure=smoke.failure, answer=smoke.answer)
            return
        log.info("smoke_passed", answer_ms=smoke.answer_ms)
        for overlap, each in () if smoke_only else todo:
            answer = await asking.ask(each)
            result = judged(overlap, answer)
            found.results.append(result)
            with (out / RESULTS_FILE).open("a", encoding="utf-8", newline="\n") as file:
                file.write(result.model_dump_json() + "\n")
            log.info(
                "overlap_done",
                done=len(found.results),
                of=len(todo),
                item=overlap.item,
                variant=overlap.variant,
                expected=overlap.expected,
                rule=overlap.rule,
                arm=result.arm,
                answer=answer.answer,
                failure=answer.failure,
                answer_ms=None if answer.answer_ms is None else round(answer.answer_ms),
            )
    except CapReachedError:
        found.stopped = "cap"
        log.warning("cap_reached", done=len(found.results), of=len(todo))
    except DayLimitError:
        found.stopped = "day_limit"
        log.warning("day_limit_reached", done=len(found.results), of=len(todo))
    except RateLimitedError:
        found.stopped = "rate_limited"
        log.error("still_rate_limited", done=len(found.results), of=len(todo))
    finally:
        await asking.model.aclose()
