"""The ports: the protocols an outside service is reached through, and their data types (the
design's 6.1). Stable (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.ports.speech_to_text import (
    AudioClip,
    DataFlow,
    SpeechToText,
    Transcript,
)

__all__ = ["AudioClip", "DataFlow", "SpeechToText", "Transcript"]
