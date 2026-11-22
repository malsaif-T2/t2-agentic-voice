"""The flight agent's text-to-speech, as settings.py's `for_the_app` sets it, each part unless the
environment sets it:

- **Groq's Orpheus** (`TTS_PROVIDER`), in its default voices (abdullah for both Arabic presets,
  troy for English; core/settings/tts_voices.py), by the owner's ruling of 2026-11-18: "we would
  like to get back to our Groq voice TTS because we still have credits there". ElevenLabs stays
  the library's default (D-114) and Scribe the speech-to-text; `T2V_TTS__PROVIDER=elevenlabs`
  speaks in the owner's ElevenLabs voice again.
- **Numbers said in the caller's register** (`SPOKEN_NUMBERS`, D-107): "14:00" is said
  «ثنتين الظهر» to a Saudi caller and "two in the afternoon" in English, never digit by digit,
  since the lean agent writes times and fares in digits.
- **An Arabic clause of an English reply in the Arabic voice** (`VOICE_BY_SCRIPT`,
  `tts.voice_by_script`): the owner's calls of 2026-11-22 had two Arabic replies to English
  small talk read by orpheus-v1-english; now such a clause is said by abdullah with Saudi
  numbers, while an Arabic reply keeps abdullah through a Latin name («flynas XY 299»).
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import TtsSettings

TTS_PROVIDER: Final = "groq"
SPOKEN_NUMBERS: Final = "by_register"
VOICE_BY_SCRIPT: Final = True


def app_tts(tts: TtsSettings) -> TtsSettings:
    """`tts` as the app speaks (the module's docstring); a provider set by the environment keeps
    its own voices, and a voice map set keeps itself."""
    update: dict[str, object] = {}
    if "spoken_numbers" not in tts.model_fields_set:
        update["spoken_numbers"] = SPOKEN_NUMBERS
    if "voice_by_script" not in tts.model_fields_set:
        update["voice_by_script"] = VOICE_BY_SCRIPT
    if "provider" not in tts.model_fields_set:
        update["provider"] = TTS_PROVIDER
    if not update:
        return tts
    data = tts.model_dump() | update
    # The settings fill an unset voice map with the provider's own, so a map that is the old
    # provider's default gives way to the new one's, never its voices kept.
    if "provider" in update and tts.languages == TtsSettings(provider=tts.provider).languages:
        del data["languages"]
    return TtsSettings.model_validate(data)
