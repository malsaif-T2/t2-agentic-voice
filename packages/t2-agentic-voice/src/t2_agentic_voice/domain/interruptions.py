"""Whether the caller's speech over the agent's reply stops it (the design's 3.1; plan 005's "The
starting rule"): under `interruptions.mode = "two_step"`, the session judges each transcript of an
overlap with `judge`, its window's first, then its whole overlap's when the window did not stop
the agent. Pure, with no IO: the language's words (domain/words.py), the filter for text from
silence (domain/silence.py) and the `interruptions` group's bounds come in its arguments, so
domain reads no settings group.

The rule's steps, in order, after the canonical normalization: no words, or text from silence:
go on; a stop word or a word asking the agent to pause, or a stop word as Whisper mishears it:
stop; a repeat word: stop, then say the last reply again; the agent's own words (each within one
edit of a word of the clauses that played): go on; listening sounds only: go on; a short output
(at most `short_words` words, under `short_s` of speech, none a listed word): go on; at least
`min_words` words: stop; fewer: go on. Plan 005's Track A builds it; until then `judge` raises.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.events import InterruptionKind
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.words import Words

# What the session does with the reply an overlap spoke over: stop it, stop it and say the last
# reply again, or let it go on (and bring the agent's voice back).
OverlapAction = Literal["stop", "repeat", "go_on"]
# Which step of the rule decided, in its order: for the trace and the scorecards, never the
# words themselves.
VerdictReason = Literal[
    "no_words",
    "stop_word",
    "repeat_word",
    "own_words",
    "listening",
    "short_output",
    "enough_words",
    "too_few_words",
]


class Overlap(BaseModel):
    """One transcript of an overlap, as the rule judges it: its `text`; the probability Whisper
    gave that the audio holds no speech (None when the provider gave none); `speech_s`, the
    seconds of speech it was taken from; `played`, the texts of the agent's clauses that played
    in the last `interruptions.own_words_s`, which its own voice heard back would say; and
    `language`, the call's primary code, whose words apply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)
    speech_s: float = Field(ge=0, allow_inf_nan=False)
    played: tuple[str, ...] = ()
    language: LanguageCode


class Verdict(BaseModel):
    """What the rule decided for an overlap: its `action`; the `kind` of the `Interrupted` event
    a stop gives (`false` when the reply goes on); and the step that decided (`reason`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: OverlapAction
    kind: InterruptionKind
    reason: VerdictReason


def judge(
    overlap: Overlap,
    *,
    words: Words,
    no_speech_max: float | None,
    captions: Collection[str],
    min_words: int,
    short_words: int,
    short_s: float,
) -> Verdict:
    """The rule's verdict on `overlap`, with the call language's `words` (the agent's, a team's
    additions included), the filter for text from silence (`no_speech_max`, None for off, and
    the `captions` it counts as no words, none for off) and the rule's bounds."""
    raise NotImplementedError("the starting rule is plan 005's Track A's to build")
