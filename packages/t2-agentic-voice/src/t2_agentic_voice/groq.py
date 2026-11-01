"""Groq's adapters behind the ports: its Whisper speech-to-text today (D-004). Stable (D-021).
A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.adapters.groq_stt import GroqSTT

__all__ = ["GroqSTT"]
