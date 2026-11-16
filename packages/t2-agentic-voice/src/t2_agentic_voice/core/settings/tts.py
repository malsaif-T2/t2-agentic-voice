"""The `tts` group: text-to-speech, a model and a voice for each language."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN, Group

TtsProvider = Literal["groq"]
# The declaration's language presets (the design's 5.2): Saudi Arabic, MSA and English.
LanguageTag = Literal["ar-SA", "ar", "en"]
# How a reply's numbers, times and dates are said (`TtsSettings.spoken_numbers`).
SpokenNumbers = Literal["as_written", "by_register"]
# Groq's Orpheus models (the design's 7.6).
TtsModel = Literal["canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english"]
_ARABIC: TtsModel = "canopylabs/orpheus-arabic-saudi"
_ENGLISH: TtsModel = "canopylabs/orpheus-v1-english"


class TtsVoice(Group):
    """The model and the voice one language is spoken in."""

    model: TtsModel = Field(description="The Orpheus model.")
    # A voice's name as the model lists it: a lowercase word. Whether the model has it is
    # checked against the provider at runtime start, not here.
    voice: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$", description="The model's voice.")


def _voices() -> dict[LanguageTag, TtsVoice]:
    """The owner's voices (plan 003, Q5): abdullah for both Arabic presets, troy for English."""
    return {
        "ar-SA": TtsVoice(model=_ARABIC, voice="abdullah"),
        "ar": TtsVoice(model=_ARABIC, voice="abdullah"),
        "en": TtsVoice(model=_ENGLISH, voice="troy"),
    }


class TtsSettings(Group):
    """Text-to-speech: the adapter, a model and a voice for each language, and what is done
    with the audio."""

    provider: TtsProvider = Field(
        default="groq",
        description="Which adapter turns text into speech; only Groq's exists for now (D-004).",
    )
    languages: Annotated[Mapping[LanguageTag, TtsVoice], FROZEN, PLAIN] = Field(
        default_factory=_voices,
        validate_default=True,
        description=(
            "The model and voice of each language preset (ar-SA, ar, en), as a JSON object: "
            '{"en": {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}}. A value '
            "replaces the whole map."
        ),
    )
    timeout_s: float = Field(
        default=6.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest one synthesis request may take before it is a timeout.",
    )
    cache_phrases: bool = Field(
        default=True,
        description=(
            "Whether the fixed phrases declared at start (greetings, notices) are synthesized "
            "once and cached under the storage folder."
        ),
    )
    cache_clauses: bool = Field(
        default=True,
        description=(
            "Whether every clause the agent speaks in a call with a talker is kept on disk under "
            "the storage folder by its exact text, its language, its voice and the adapter that "
            "made it, so the same clause plays again with no request; the echo's words said back "
            "are never kept. On by default, as the owner ruled: it costs only disk, bounded by "
            "clause_cache_mb."
        ),
    )
    clause_cache_mb: int = Field(
        default=512,
        ge=1,
        description=(
            "The most disk the clause cache keeps, in megabytes; past it, the clauses played "
            "longest ago are removed."
        ),
    )
    spoken_numbers: SpokenNumbers = Field(
        default="as_written",
        description=(
            "How a reply's numbers, times and dates are said: as_written reads each run of "
            "digits as a number (num2words' MSA in Arabic) or an ID; by_register says them in "
            "the caller's register, Saudi or MSA words in Arabic, a time as a clock says it "
            "with its part of the day, an ISO date with its weekday and month."
        ),
    )
    spoken_key_combinations: bool = Field(
        default=False,
        description=(
            "Whether a key combination in a reply is said as its keys, its plus signs left out "
            '("Ctrl + Shift + R" is said "Control Shift R"; in Arabic, by the Arabic names of '
            "its keys); off, it is said as written."
        ),
    )
    trim_silence: bool = Field(
        default=False,
        description=(
            "Whether the silence the model puts before its speech is trimmed; off, the audio "
            "plays as it comes."
        ),
    )
