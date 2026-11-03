"""The `interruptions` group: what the agent does when the caller speaks over its reply (the
design's 7.6; plan 005).

Under `drop`, the default until the registered runs move it (GP-18), a turn that began over a
reply is not answered, as before. Under `two_step`, the agent's voice is lowered at once
(`duck_level`), the overlap is transcribed in a first window (`first_window_ms`) and then whole,
and the session's rule decides from each transcript whether to stop: the bounds below are the
rule's (plan 005's "The starting rule"). The duck level is the prototype's (its `web/voice.js`,
line 174, `duck(level = 0.25)`, read 2026-11-03); the window is plan 002's run W3; the other
bounds are the prototype's (its D30) and the starting rule's, none measured on the library yet.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

# How speech over a reply is taken: not answered (`drop`), or ducked and judged (`two_step`).
InterruptionMode = Literal["drop", "two_step"]


class InterruptionSettings(Group):
    """Interruptions: how the caller's speech over the agent's reply is taken, and the bounds of
    the rule that decides whether it stops the agent."""

    mode: InterruptionMode = Field(
        default="drop",
        description=(
            "How the caller's speech over the agent's reply is taken: drop (the turn is not "
            "answered, so the agent never answers its own voice) or two_step (the agent's voice "
            "is lowered, the speech transcribed, and the agent stops only when the rule says "
            "so). A registered measurement moves the default (GP-18)."
        ),
    )
    duck_level: float = Field(
        default=0.25,
        ge=0,
        le=1,
        allow_inf_nan=False,
        description=(
            "How loud the agent's reply plays while the caller speaks over it, until the speech "
            "is judged, from 0 (silent) to 1 (unchanged)."
        ),
    )
    first_window_ms: int = Field(
        default=750,
        gt=0,
        description=(
            "The first part of the speech over a reply sent to speech-to-text before the caller "
            "has finished, counted from 300 ms before the speech detector heard it begin."
        ),
    )
    min_words: int = Field(
        default=2,
        ge=1,
        description="The fewest words over a reply that stop the agent when none is a listed word.",
    )
    short_words: int = Field(
        default=2,
        ge=0,
        description=(
            "The most words a short output holds: at most this many, under short_s of speech, "
            "and none a stop, repeat or no word, the agent goes on (a listening sound misheard)."
        ),
    )
    short_s: float = Field(
        default=1.6,
        gt=0,
        allow_inf_nan=False,
        description="The speech a short output stays under, for the agent to go on.",
    )
    own_words_s: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
        description=(
            "How far back the agent's own words count: speech over a reply whose words are "
            "those of the clauses played this long before is its own voice, heard back."
        ),
    )
