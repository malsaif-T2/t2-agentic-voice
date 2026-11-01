"""What a recall scorer returns: how many of the expected things an output holds.

A count, not a rate, so the counts of many outputs add up before they are divided (pooled), as a
stratum's recall is. Public through the `evals` facade (D-021).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Recall(BaseModel):
    """Of `expected` things (product terms, ticket numbers) in a reference, `found` were in the
    output too."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: int = Field(ge=0)
    found: int = Field(ge=0)

    @model_validator(mode="after")
    def _found_among_expected(self) -> Recall:
        if self.found > self.expected:
            raise ValueError("found counts only expected things, so it is never above expected")
        return self
