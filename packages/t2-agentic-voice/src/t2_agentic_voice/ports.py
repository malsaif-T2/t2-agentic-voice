"""The ports: the protocols an outside service is reached through, and their data types (the
design's 6.1, 6.3, 6.4 and 6.5). Stable (D-021), `UsedTokens`, `KnowledgeBase` and `Outbox`
provisional (the design's 5.1), as are `LanguageClassifier` and `LanguageScores` (D-086). A
facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatMessage,
    ChatModel,
    ChatRequest,
    Done,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
)
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext, UsedTokens
from t2_agentic_voice.domain.ports.knowledge import KnowledgeBase, Passage
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier, LanguageScores
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry
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
    "ChatEvent",
    "ChatMessage",
    "ChatModel",
    "ChatRequest",
    "DataFlow",
    "Done",
    "IdentityVerifier",
    "JoinContext",
    "KnowledgeBase",
    "LanguageClassifier",
    "LanguageScores",
    "Outbox",
    "OutboxEntry",
    "Passage",
    "SpeechToText",
    "TextDelta",
    "TextToSpeech",
    "ToolCallRequest",
    "ToolSchema",
    "Transcript",
    "Usage",
    "UsedTokens",
]
