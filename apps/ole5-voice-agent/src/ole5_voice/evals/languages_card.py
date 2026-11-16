"""What a pass of `poe eval-languages` records (plan 007's run H, its H1; scored by
languages_score.py): the pass itself (`LanguagesRun`), each variant's turns with its strata and,
for a paused request, its turn ends judged against the owner's mark (`LanguageResult`, one line
of a pass's `TURNS_FILE`), its numbers (`LanguagesCard`, by call language `CallCard`), its
scorecard, aggregates only for a held-out pass (`LanguagesScorecard`), and its history line
(`LanguagesLine`, which spends only in a provider's pass, with its price and what it sent at
the most). The three call languages (`CALLS`) are the ordinary
call (`label`: English items in an English call, the rest in an Arabic one, `call_code`), an
Arabic call and an English one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Literal, Self, get_args

from pydantic import Field, model_validator
from t2_agentic_voice import evals

from ole5_voice.evals.eot_score import EotMetrics, Judged
from ole5_voice.evals.models import Commit, Device, Kind, Language, Model, Name, Sha256, Split
from ole5_voice.evals.runs import Note, Shown

# The call languages a pass's choices are read for: the item's own, Arabic, English.
CallLanguage = Literal["label", "ar", "en"]
CALLS: Final[tuple[CallLanguage, ...]] = get_args(CallLanguage)
# A pass's classifier: none (`session`), Silero's or ECAPA's, Whisper's own detection
# (`detected`, D-038's amendment: each turn records whether it also went naming no language), or
# a speech-to-text provider's own language (provider_language.py's `PROVIDERS`, which a test ties
# to these).
ClassifierName = Literal["off", "silero", "ecapa", "detected", "groq", "elevenlabs", "soniox"]
_Usd = Annotated[float, Field(ge=0, allow_inf_nan=False)]
TURNS_FILE: Final = "turns.jsonl"  # every variant's turns, in a dev pass and a held-out one
PAUSED_KIND: Final = "paused_request"
_Ms = Annotated[float, Field(allow_inf_nan=False)]


def call_code(call: CallLanguage, language: Language) -> str:
    """The code a call of `call` is held in for an item of `language`: the ordinary call's is
    English for an English item and Arabic for the rest."""
    if call != "label":
        return call
    return "en" if language == "english" else "ar"


class LanguagesRun(Model):
    """What a pass was: when, at which commit, on which split and data, with which classifier,
    settings and rule (Q20's registered numbers), the language its calls were held in
    (`held_in`), the silence fed around each clip, the process's peak memory where the platform
    tells it, and why; for a provider's pass, its price per hour of audio and what it sent at
    the most (provider_language.py)."""

    name: Name
    started_at: datetime
    commit: Commit
    split: Split
    classifier: ClassifierName
    settings: Shown
    data_digest: Sha256
    lead_s: float = Field(ge=0, allow_inf_nan=False)
    tail_s: float = Field(ge=0, allow_inf_nan=False)
    from_s: float = Field(gt=0, allow_inf_nan=False)
    min_share: float = Field(gt=0, le=1, allow_inf_nan=False)
    threads: int = Field(ge=1)
    held_in: Literal["ar", "en"]
    note: Note
    peak_mb: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_per_hour_usd: _Usd | None = None
    billed_seconds: _Usd = 0
    cost_usd: _Usd = 0


class LanguageResult(Model):
    """One variant of a pass: its strata, each turn's record and, for a paused request, its
    turn ends judged against the owner's mark."""

    item: Name
    variant: Name
    split: Split
    kind: Kind
    language: Language
    device: Device
    turns: tuple[evals.LanguageTurn, ...]
    judged: Judged | None = None


class Changed(Model):
    """One item language's variants in a call language, and how many the rule changed."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    changed: int = Field(ge=0)


class CallCard(Model):
    """One call language's numbers (the module's docstring)."""

    changed: int = Field(ge=0)
    mixed: int = Field(ge=0)
    by_language: dict[str, Changed] = Field(default_factory=dict)


class LanguagesCard(Model):
    """A pass's numbers (the module's docstring)."""

    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    turns: int = Field(ge=0)
    by: dict[str, int]
    in_time: int = Field(ge=0)
    late: int = Field(ge=0)
    never: int = Field(ge=0)
    verdict_median_ms: _Ms | None = None
    verdict_p90_ms: _Ms | None = None
    late_median_ms: _Ms | None = None
    late_max_ms: _Ms | None = None
    paused: EotMetrics
    calls: dict[CallLanguage, CallCard]
    disagreements: int = Field(ge=0)


class LanguagesScorecard(Model):
    """A pass's scorecard: its numbers and, in a dev pass, each variant, refused as it is read
    for a held-out pass that holds one."""

    run: LanguagesRun
    speakers: Literal["one speaker"] = "one speaker"  # the owner alone (D-006)
    complete: bool
    card: LanguagesCard
    variants: tuple[LanguageResult, ...] = ()

    @model_validator(mode="after")
    def _held_out_aggregates_only(self) -> Self:
        held_out = self.run.split == "held-out"
        if held_out and (self.variants or any(c.by_language for c in self.card.calls.values())):
            raise ValueError("a held-out pass's scorecard holds aggregates only")
        return self


class LanguagesLine(Model):
    """One line of `history.jsonl` for a pass of `poe eval-languages`: its numbers, in counts
    and times, and, for a provider's pass, its price and what it sent at the most."""

    kind: Literal["languages"] = "languages"
    time: datetime
    commit: Commit
    run: Name
    classifier: ClassifierName
    settings: Shown
    split: Split
    items: int = Field(ge=0)
    variants: int = Field(ge=0)
    turns: int = Field(ge=0)
    by: dict[str, int]
    in_time: int = Field(ge=0)
    late: int = Field(ge=0)
    verdict_median_ms: _Ms | None
    late_median_ms: _Ms | None
    cut_offs: int = Field(ge=0)
    misses: int = Field(ge=0)
    delay_median_ms: _Ms | None
    changed: dict[CallLanguage, int]
    mixed: dict[CallLanguage, int]
    disagreements: int = Field(ge=0)
    peak_mb: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_per_hour_usd: _Usd | None = None
    billed_seconds: _Usd = 0
    cost_usd: _Usd = 0
    scorecard: str
    data_digest: Sha256
    note: Note
    complete: bool
