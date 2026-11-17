"""The `tts` group: text-to-speech, the adapter, a model and a voice for each language.

`provider` picks the adapter: ElevenLabs' v4 Turbo, the default by the owner's ruling (D-114),
on the `elevenlabs` key that Scribe needs too; Groq's Orpheus, the fallback, on the Groq key
alone; or Telnyx, measured beside them, on its own key. `languages` holds the model and
voice of each language in the chosen provider's own names; left unset, it is that provider's
default map (core/settings/tts_voices.py), so choosing a provider is one setting, and a map
given must hold only that provider's models and voices, checked when the settings load. The
caches, the usage counts and the doctor read the voices from `languages`, whichever provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN, Group
from t2_agentic_voice.core.settings.tts_voices import (
    DEFAULT_PROVIDER,
    LanguageTag,
    SpokenNumbers,
    TtsModel,
    TtsProvider,
    TtsVoice,
    default_voices,
    misfit,
)

__all__ = [
    "DEFAULT_PROVIDER",
    "LanguageTag",
    "SpokenNumbers",
    "TtsModel",
    "TtsProvider",
    "TtsSettings",
    "TtsVoice",
]


class TtsSettings(Group):
    """Text-to-speech: the adapter, a model and a voice for each language, and what is done
    with the audio."""

    provider: TtsProvider = Field(
        default=DEFAULT_PROVIDER,
        description=(
            "Which adapter turns text into speech: elevenlabs (v4 Turbo in the owner's voice for "
            "Saad, the default, D-114; it needs T2V_ELEVENLABS__API_KEY, as Scribe does), groq "
            "(Orpheus, the fallback, on the Groq key alone) or telnyx (Bayan, measured beside "
            "them; it needs T2V_TELNYX__API_KEY). With tts.languages unset, each language is "
            "spoken in the chosen provider's default model and voice."
        ),
    )
    languages: Annotated[Mapping[LanguageTag, TtsVoice], FROZEN, PLAIN] = Field(
        default_factory=lambda: default_voices(DEFAULT_PROVIDER),
        validate_default=True,
        description=(
            "The model and voice of each language preset (ar-SA, ar, en), in tts.provider's own "
            'names, as a JSON object: {"en": {"model": "canopylabs/orpheus-v1-english", "voice": '
            '"troy"}}. A value replaces the whole map; unset, it is the provider\'s default map.'
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _provider_default(cls, data: Any) -> Any:
        """With `languages` unset, the chosen provider's default map (the module's docstring)."""
        if isinstance(data, Mapping) and "languages" not in data:
            provider = data.get("provider", DEFAULT_PROVIDER)
            if isinstance(provider, str):
                return {**data, "languages": default_voices(provider)}
        return data

    @field_validator("languages")
    @classmethod
    def _of_provider(
        cls, value: Mapping[LanguageTag, TtsVoice], info: ValidationInfo
    ) -> Mapping[LanguageTag, TtsVoice]:
        provider = info.data.get("provider")
        for tag, voice in value.items():
            problem = misfit(provider, voice) if isinstance(provider, str) else None
            if problem:
                raise ValueError(f"the voice of {tag} {problem}")
        return value

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
