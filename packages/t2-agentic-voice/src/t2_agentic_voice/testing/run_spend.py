"""What a measurement run that spends has spent, by model, and the cap no request may take it
past: `Price` (USD per million tokens read and written, the cached tokens at the input price),
`Spend` (each model's requests and tokens this session, what earlier sessions of a resumed run
spent, and `check`, `CapReachedError` before a request whose budgeted cost would pass the cap),
and `ModelSpend`, one model's spend as a run keeps it in its files: strict, read-only, and an
error that never echoes the value it refused. Public through the `evals` facade.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field


class CapReachedError(Exception):
    """The next request's budgeted cost would take the run past its cap."""


@dataclass(frozen=True)
class Price:
    """A model's price: USD per million tokens read and written."""

    input_usd: float
    output_usd: float

    def of(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_usd + output_tokens * self.output_usd) / 1e6


class ModelSpend(BaseModel):
    """What a run sent to one model: its requests, those that were a retry of one turned away,
    those that failed after every attempt, those whose provider reported no usage (counted at
    their budget), the tokens read (the cached among them counted again) and written, and their
    cost at the run's prices."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    model: str = Field(min_length=1, max_length=128)
    requests: int = Field(default=0, ge=0)
    retried: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    unreported: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0, allow_inf_nan=False)


@dataclass
class ModelUse:
    """One model's counts this session, as `PacedChat` adds to them."""

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
    _uses: dict[str, ModelUse] = field(default_factory=dict)

    def use(self, model: str) -> ModelUse:
        if model not in self.prices:
            raise ValueError(f"the run has no price for the model {model}")
        return self._uses.setdefault(model, ModelUse())

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
