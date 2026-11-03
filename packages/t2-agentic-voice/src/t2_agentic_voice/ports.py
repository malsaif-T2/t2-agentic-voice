"""The ports: the protocols an outside service is reached through, and their data types (the
design's 6.1 and 6.5). Stable (D-021), `UsedTokens` provisional (the design's 5.1). A facade: it
only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext, UsedTokens
from t2_agentic_voice.domain.ports.speech_to_text import (
    AudioClip,
    DataFlow,
    SpeechToText,
    Transcript,
)
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

__all__ = [
    "AudioChunk",
    "AudioClip",
    "DataFlow",
    "IdentityVerifier",
    "JoinContext",
    "SpeechToText",
    "TextToSpeech",
    "Transcript",
    "UsedTokens",
]
