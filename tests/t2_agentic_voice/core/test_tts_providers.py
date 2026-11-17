"""The `tts` group's provider choice (D-114): ElevenLabs the default in the owner's voice, Groq's
Orpheus the fallback with its own voices; each provider, with `tts.languages` unset, speaks in
its own default map; a map given must hold that provider's models and voices, refused naming the
setting and never the value."""

from __future__ import annotations

from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.core.settings.tts_voices import default_voices, misfit


def _voices(**tts: Any) -> dict[str, tuple[str, str]]:
    settings = VoiceSettings.model_validate({"env": "test", "tts": tts})
    return {tag: (voice.model, voice.voice) for tag, voice in settings.tts.languages.items()}


def test_elevenlabs_is_the_default_and_groq_the_fallback_with_its_own_voices() -> None:
    groq = {
        "ar-SA": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "ar": ("canopylabs/orpheus-arabic-saudi", "abdullah"),
        "en": ("canopylabs/orpheus-v1-english", "troy"),
    }
    assert TtsSettings().provider == "elevenlabs"
    assert _voices() == _voices(provider="elevenlabs") != groq == _voices(provider="groq")


def test_another_provider_with_no_map_speaks_its_own_default_voices() -> None:
    eleven = _voices(provider="elevenlabs")  # the owner's pick for Saad, one voice for all
    assert set(eleven.values()) == {("eleven_v4_turbo", "nhJWWCFdNdusuVUT3x19")}
    telnyx = _voices(provider="telnyx")
    assert telnyx == {
        "ar-SA": ("Telnyx.Bayan", "Fahd"),
        "ar": ("Telnyx.Bayan", "Fahd"),
        "en": ("Telnyx.Bayan", "Michael"),
    }
    for provider in ("groq", "elevenlabs", "telnyx"):
        assert all(misfit(provider, v) is None for v in default_voices(provider).values())


def test_a_map_given_replaces_the_providers_default() -> None:
    given = {"en": {"model": "eleven_flash_v2_5", "voice": "nPczCjzI2devNBz1zQrb"}}
    assert _voices(provider="elevenlabs", languages=given) == {
        "en": ("eleven_flash_v2_5", "nPczCjzI2devNBz1zQrb")
    }


SECRET = "MadeUpVoiceSecret4471"
MISFITS = [
    ("elevenlabs", {"model": "canopylabs/orpheus-v1-english", "voice": "troy"}),
    ("groq", {"model": "eleven_v4_turbo", "voice": SECRET}),
    ("groq", {"model": "canopylabs/orpheus-v1-english", "voice": SECRET}),
    ("telnyx", {"model": "eleven_v4", "voice": SECRET}),
    ("elevenlabs", {"model": "eleven_v4", "voice": f"{SECRET}.x"}),
    ("telnyx", {"model": "Telnyx.Bayan", "voice": f"{SECRET}.x"}),
]


@pytest.mark.parametrize(("provider", "voice"), MISFITS)
def test_a_voice_of_another_provider_is_refused_naming_the_setting_only(
    provider: str, voice: dict[str, str]
) -> None:
    with pytest.raises(ConfigurationError) as raised:
        VoiceSettings.model_validate(
            {"env": "test", "tts": {"provider": provider, "languages": {"en": voice}}}
        )
    message = raised.value.message
    assert "T2V_TTS__LANGUAGES" in message and SECRET not in message
