"""The `tts` group: text-to-speech, a model and a voice for each language."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN, Group

TtsProvider = Literal["groq"]
# The declaration's language presets (the design's 5.2): Saudi Arabic, MSA and English.
LanguageTag = Literal["ar-SA", "ar", "en"]
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
    trim_silence: bool = Field(
        default=False,
        description=(
            "Whether the silence the model puts before its speech is trimmed; off, the audio "
            "plays as it comes."
        ),
    )
