"""The `guard` group: the output guard's ID rule (the design's 8.2, rule B; plan 006): which
tokens of a clause are ID-shaped, and what a blocked clause drops; the phrases added to the
claim rule's default list (rule A; plan 007); and whether a script none of the agent's languages
writes is taken out of what the talker writes before the guard reads it (agent/stray_script.py).
Every clause the talker writes is checked before text-to-speech, and so is a card's text; the
runtime's own templates are not.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from t2_agentic_voice.core.settings.base import Group
from t2_agentic_voice.core.settings.words import WordLists

# What a blocked clause drops: it and the rest of the reply, or only it.
OnBlock = Literal["drop_rest", "drop_clause"]
# One declared ID pattern, a regular expression as Python's `re` reads it.
_Pattern = Annotated[str, Field(min_length=1, max_length=200)]


class GuardSettings(Group):
    """The output guard: what counts as an ID, and what a clause that speaks one with no
    evidence drops."""

    id_patterns: tuple[_Pattern, ...] = Field(
        default=(),
        description=(
            "More ID shapes, beside runs of min_id_digits digits, as a JSON list of regular "
            'expressions, such as ["LT-\\\\d{5}"]. A pattern that matches no text at all '
            "(the empty text) is refused. Unset: none."
        ),
    )
    min_id_digits: int = Field(
        default=3,
        ge=1,
        le=32,
        description=(
            "The fewest digits in a row, after digit words and Arabic-Indic digits are made "
            "digits, that count as an ID, which passes only with evidence from this call."
        ),
    )
    on_block: OnBlock = Field(
        default="drop_rest",
        description=(
            "What a blocked clause drops: drop_rest, it and the rest of the reply, or "
            "drop_clause, only it. A fixed phrase is spoken in its place either way."
        ),
    )

    claims: WordLists = Field(
        default_factory=dict,
        validate_default=True,
        description=(
            "Phrases added to each language's default list of what claims any action, as a "
            'JSON object from a language\'s code to a list: {"ar": ["..."]}. A value replaces '
            "the map."
        ),
    )
    remove_stray_script: bool = Field(
        default=True,
        description=(
            "Whether each character of a script none of the agent's languages writes (a "
            "Chinese character in an Arabic reply), and each pictograph, is taken out of what "
            "the talker writes, its tool calls' arguments included, before the guard reads it, "
            "and a digit of another script written as its ASCII digit; the voice, the "
            "captions, the history, the trace and the events then hold the text without it. "
            "Off: kept as written."
        ),
    )

    @field_validator("id_patterns")
    @classmethod
    def _patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, pattern in enumerate(value):
            try:
                compiled = re.compile(pattern)
            except re.error:
                compiled = None  # its error repeats the pattern: not chained
            if compiled is None:
                raise ValueError(f"pattern {index} is not a regular expression Python reads")
            if compiled.fullmatch(""):
                raise ValueError(f"pattern {index} matches the empty text, so every clause")
        return value
