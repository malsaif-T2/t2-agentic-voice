"""What the flight page may choose for a call under Options (`CALL_OPTIONS`, given to the
library's runtime as `VoiceRuntime(call_options=...)`, served at `/voice/choices` with
`server.call_choices` on, which settings.py's `for_the_app` turns on unless set), by the owner's
request of 2026-11-22: "Can you add choices to choose the STT (whisper, elevenlabs), the LLM
model and the TTS model (canopylabs, Elevenlabs v4/turbo, and telnyx bayan (Jasem)). Make it
under Options."

- **Speech-to-text**: Groq's Whisper (`whisper-large-v3`) or ElevenLabs' Scribe (`scribe_v3`).
- **Model**: today's `openai/gpt-oss-120b` on Groq at effort medium, or OpenAI's gpt-5.5,
  gpt-6-luna and gpt-5.4-mini, each at effort none: OpenAI's Chat Completions take the talker's
  function tools with no other effort (the library's `EFFORTS`). The yes rule's check and the
  uncertain overlap stay on Groq's gpt-oss-120b whatever the model.
- **Voice**: Canopy Labs' Orpheus on Groq (abdullah for both Arabic presets, troy for English);
  ElevenLabs' v4 Turbo or v4, both in the owner's voice (the library's ElevenLabs default,
  D-114); Telnyx's Bayan, Jasem for both Arabic presets and Michael for English.

The Groq ones need only the Groq key the server needs anyway; the others their own provider's.
The library's menu lists only the offers whose key the server holds, never a key or its file,
and each group's default is the offer the settings run on (no pick, no change), so a server with
the Groq key alone offers Whisper, gpt-oss-120b and Orpheus.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import TtsSettings, TtsVoice
from t2_agentic_voice.server import CallOptions, ModelOffer, SttOffer, VoiceOffer

__all__ = ["BAYAN", "CALL_OPTIONS"]

# Telnyx's voice family the Bayan voices belong to.
BAYAN: Final = "Telnyx.Bayan"
# The owner's ElevenLabs voice in v4 Turbo, the library's ElevenLabs default (D-114).
_ELEVENLABS: Final = TtsSettings(provider="elevenlabs").languages

CALL_OPTIONS: Final = CallOptions(
    stt=(
        SttOffer(id="whisper", provider="groq", model="whisper-large-v3"),
        SttOffer(id="scribe", provider="elevenlabs", model="scribe_v3"),
    ),
    models=(  # OpenAI's take function tools only with effort none (the module's docstring)
        ModelOffer(id="gpt-oss-120b", model="openai/gpt-oss-120b", reasoning_effort="medium"),
        ModelOffer(id="gpt-5.5", model="gpt-5.5", reasoning_effort="none"),
        ModelOffer(id="gpt-6-luna", model="gpt-6-luna", reasoning_effort="none"),
        ModelOffer(id="gpt-5.4-mini", model="gpt-5.4-mini", reasoning_effort="none"),
    ),
    voices=(
        VoiceOffer(id="orpheus", provider="groq", languages=TtsSettings(provider="groq").languages),
        VoiceOffer(id="eleven-v4-turbo", provider="elevenlabs", languages=_ELEVENLABS),
        VoiceOffer(
            id="eleven-v4",
            provider="elevenlabs",
            languages={
                tag: TtsVoice(model="eleven_v4", voice=voice.voice)
                for tag, voice in _ELEVENLABS.items()
            },
        ),
        VoiceOffer(
            id="telnyx-bayan",
            provider="telnyx",
            languages={
                "ar-SA": TtsVoice(model=BAYAN, voice="Jasem"),
                "ar": TtsVoice(model=BAYAN, voice="Jasem"),
                "en": TtsVoice(model=BAYAN, voice="Michael"),
            },
        ),
    ),
)
