"""The spoken-language classifier port (plan 007's Block H): a few seconds of a turn's speech in,
the share of each language asked out, so each turn can be sent to speech-to-text in the
language the caller spoke (domain/turn_language.py's rule).

A classifier runs in the process, on the CPU: it sends no audio anywhere and keeps none
(invariant 8). Its answer is parsed here (`LanguageScores`, `scores_for`; invariant 4): a share
for each code asked and no other, each from 0 to 1, summing to 1, with `mass`, the share of the
model's whole output those codes held, so a classifier sure of a third language still chooses
only between the agent's, its low mass kept. An answer that does not parse is a failure.
`classify` returns None when the classifier is busy with another turn (one classification at a
time a process), and raises `ProviderError` when it fails. Public through the `ports` facade;
provisional.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

# How far from 1 the shares may sum, float rounding aside.
SUM_TOLERANCE = 1e-6


def _malformed() -> ProviderError:
    """An answer that does not parse: a failure, never asked again."""
    return ProviderError("server_error", False)


class LanguageScores(BaseModel):
    """A classifier's answer for one clip: `shares`, each code asked with its share, from 0 to 1,
    summing to 1; and `mass`, the share of the model's whole output the codes held, from 0 to 1.
    Build one with `parsed` or `renormalized`, which refuse what does not parse."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    shares: Mapping[str, float]
    mass: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def _a_distribution(self) -> Self:
        values = list(self.shares.values())
        if not values:
            raise ValueError("an answer holds a share for each code asked")
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
            raise ValueError("each share is from 0 to 1")
        if abs(sum(values) - 1) > SUM_TOLERANCE:
            raise ValueError("the shares sum to 1")
        return self

    @property
    def best(self) -> tuple[str, float]:
        """The code with the largest share, and its share (the first such code asked)."""
        code = max(self.shares, key=lambda each: self.shares[each])
        return code, self.shares[code]

    @classmethod
    def parsed(cls, shares: Mapping[str, object], *, among: Sequence[str], mass: object) -> Self:
        """The answer of shares by code for the codes `among`, or a `ProviderError` when it does
        not parse: a code not asked or one missing, a share that is not a number from 0 to 1,
        shares that do not sum to 1, a mass outside 0 to 1."""
        if set(shares) != set(among) or len(set(among)) != len(among):
            raise _malformed()
        try:
            return cls.model_validate({"shares": dict(shares), "mass": mass})
        except ValidationError:
            raise _malformed() from None

    @classmethod
    def renormalized(cls, probabilities: Mapping[str, float], *, among: Sequence[str]) -> Self:
        """The answer from the probabilities the model gave the codes `among`, out of its whole
        output: each divided by their sum, which is the mass. A `ProviderError` when they cannot
        be (a code missing, a value not a probability, a sum of 0 or past 1)."""
        if set(probabilities) != set(among):
            raise _malformed()
        values = [float(probabilities[code]) for code in among]
        total = sum(values)
        if not all(math.isfinite(v) and v >= 0 for v in values) or not 0 < total <= 1 + 1e-6:
            raise _malformed()
        shares = {code: value / total for code, value in zip(among, values, strict=True)}
        return cls.parsed(shares, among=among, mass=min(total, 1.0))


def scores_for(answer: object, *, among: Sequence[str]) -> LanguageScores | None:
    """A classifier's `answer` to a clip of the codes `among`, as the port takes it: None for a
    busy classifier; the scores when they hold exactly those codes; a `ProviderError` for
    anything else."""
    if answer is None:
        return None
    if not isinstance(answer, LanguageScores) or set(answer.shares) != set(among):
        raise _malformed()
    return answer


class LanguageClassifier(Protocol):
    """A spoken-language classifier behind the port. `name` identifies it in logs and traces."""

    name: str

    async def load(self, among: Sequence[str]) -> None:
        """Load the model, off the event loop, once a process; a ConfigurationError, before any
        call, when its files are missing or changed, or it cannot hear a code of `among`."""

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        """The share of each code of `among` in `clip`; None when it is busy with another
        clip. Raises `ProviderError` on a failure; a cancel stops waiting at once."""

    async def aclose(self) -> None:
        """Let the model go; called once, when its owner (the runtime, a run) is done."""
