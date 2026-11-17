"""The text-to-speech providers' models and voices (D-114), which `tts.languages` holds in the
chosen provider's own names, and each provider's default map.

- **Groq** (D-004), the fallback: Orpheus, `canopylabs/orpheus-arabic-saudi` for both Arabic
  presets in the voice abdullah, `canopylabs/orpheus-v1-english` in troy (the owner's, plan
  003, Q5); a voice is a lowercase word.
- **ElevenLabs**, the default (D-114): a model ID (`ElevenLabsModel`) and a voice ID, letters
  and digits as ElevenLabs writes them; by default Eleven v4 Turbo, its real-time model of the
  v4 generation, in the voice the owner picked by ear for Saad on 2026-11-17, for every language.
- **Telnyx**: the voice family (`TelnyxModel`, the voice's ID before its last dot: `Telnyx.Bayan`,
  Telnyx's Arabic model of 13 dialects and English, or `Humain`, HUMAIN's voices that Telnyx
  serves) and the voice within it; the adapter sends the two joined by a dot
  (`Telnyx.Bayan.Fahd`). By default Bayan's Saudi Fahd for Arabic and its English Michael.

`misfit` says why a voice does not fit a provider, for the settings' own check; `default_voices`
gives a provider's map. Whether the provider has a voice is checked against the provider at the
runtime's start (`check_language`), not here.
"""

from __future__ import annotations

import re
from typing import Final, Literal, get_args

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

TtsProvider = Literal["groq", "elevenlabs", "telnyx"]
# The default by the owner's ruling of 2026-11-17 (D-114); Groq's Orpheus the fallback.
DEFAULT_PROVIDER: Final[TtsProvider] = "elevenlabs"
# The declaration's language presets (the design's 5.2): Saudi Arabic, MSA and English.
LanguageTag = Literal["ar-SA", "ar", "en"]
# How a reply's numbers, times and dates are said (`TtsSettings.spoken_numbers`).
SpokenNumbers = Literal["as_written", "by_register"]
# Groq's Orpheus models (the design's 7.6).
GroqModel = Literal["canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english"]
# ElevenLabs' models that speak Arabic and English (its model list, read 2026-11-17).
ElevenLabsModel = Literal[
    "eleven_v4",
    "eleven_v4_turbo",
    "eleven_v3",
    "eleven_v3_conversational",
    "eleven_multilingual_v2",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
]
# Telnyx's voice families with Saudi or MSA voices that its WebSocket speaks (its voices list,
# read 2026-11-17).
TelnyxModel = Literal["Telnyx.Bayan", "Humain"]
TtsModel = Literal[GroqModel, ElevenLabsModel, TelnyxModel]

_MODELS: Final[dict[str, frozenset[str]]] = {
    "groq": frozenset(get_args(GroqModel)),
    "elevenlabs": frozenset(get_args(ElevenLabsModel)),
    "telnyx": frozenset(get_args(TelnyxModel)),
}
_VOICES: Final[dict[str, re.Pattern[str]]] = {
    "groq": re.compile(r"[a-z][a-z0-9_-]{0,31}"),
    "elevenlabs": re.compile(r"[A-Za-z0-9]{8,40}"),
    "telnyx": re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"),
}


class TtsVoice(Group):
    """The model and the voice one language is spoken in, in the provider's own names."""

    model: TtsModel = Field(description="The provider's model (a Telnyx voice's family).")
    # Letters, digits, `_`, `-` and `.` (ElevenLabs' IDs mix cases; a Telnyx voice may hold a
    # dot); each provider's own form is held by `misfit`.
    voice: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", description="The model's voice."
    )


def misfit(provider: str, voice: TtsVoice) -> str | None:
    """Why `voice` does not fit `provider` (fixed text, never the value), or None."""
    models, form = _MODELS.get(provider), _VOICES.get(provider)
    if models is None or form is None:
        return None
    if voice.model not in models:
        return "names a model of another provider than tts.provider"
    if not form.fullmatch(voice.voice):
        return "is not written as tts.provider writes its voices"
    return None


# The owner's pick for Saad (D-114, 2026-11-17): ElevenLabs' v4 Turbo in the voice
# `nhJWWCFdNdusuVUT3x19` for both Arabic presets and English (their second choice,
# `rpGHcNQJvO8dFNNFNj1v`, matched it in price and latency). Telnyx's first voices put before the
# owner: Bayan Fahd (Saudi, male) and Michael (English, male).
ELEVENLABS_MODEL: Final = "eleven_v4_turbo"
ELEVENLABS_ARABIC: Final = "nhJWWCFdNdusuVUT3x19"
ELEVENLABS_ENGLISH: Final = "nhJWWCFdNdusuVUT3x19"
TELNYX_ARABIC: Final = "Fahd"
TELNYX_ENGLISH: Final = "Michael"


def default_voices(provider: str) -> dict[LanguageTag, TtsVoice]:
    """`provider`'s default map (the module's docstring); Groq's for a name it does not know,
    which the provider's own check then refuses."""
    if provider == "elevenlabs":
        arabic = TtsVoice(model=ELEVENLABS_MODEL, voice=ELEVENLABS_ARABIC)
        english = TtsVoice(model=ELEVENLABS_MODEL, voice=ELEVENLABS_ENGLISH)
    elif provider == "telnyx":
        arabic = TtsVoice(model="Telnyx.Bayan", voice=TELNYX_ARABIC)
        english = TtsVoice(model="Telnyx.Bayan", voice=TELNYX_ENGLISH)
    else:
        arabic = TtsVoice(model="canopylabs/orpheus-arabic-saudi", voice="abdullah")
        english = TtsVoice(model="canopylabs/orpheus-v1-english", voice="troy")
    return {"ar-SA": arabic, "ar": arabic, "en": english}
