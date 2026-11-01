"""A team's spelling guide as data: its rulings, and what a reference that breaks one gets back.

Each team writes its own guide (a golden set's references follow it), with every ruling in its
maker's words and dated; `spelling_issues` (`spelling.py`) checks a reference against it. These
types are public through the `languages` facade (D-021).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SpellingRule(BaseModel):
    """One ruling: spellings a reference must not use, and what to write instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # A stable name for the ruling, for the issues that cite it: "product-term-outlook".
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    # The spellings a reference must not hold, each a word or a phrase.
    avoid: tuple[str, ...] = Field(min_length=1)
    # What to write instead; empty when the spelling is dropped.
    write: str
    # The ruling in the words of the person who made it, quoted.
    said: str = Field(min_length=1)
    # The day it was ruled.
    on: date


class SpellingIssue(BaseModel):
    """A place where a reference breaks a ruling."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str  # the ruling's `id`
    found: str  # the spelling the reference holds
    write: str  # what the ruling says to write instead
