"""Groq's adapters behind the ports: its Whisper speech-to-text and its Orpheus text-to-speech
(D-004). Stable (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.adapters.groq_tts import GroqTTS

__all__ = ["GroqSTT", "GroqTTS"]
