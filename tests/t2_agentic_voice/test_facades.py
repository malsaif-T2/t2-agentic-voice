"""The public facades (D-021): each module of [package] facades imports, exports exactly the
names listed here, and defines none of them itself (ARCH-FACADE checks the source); and the
package root exports exactly its own list."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import t2_agentic_voice

from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
# Every public name the facades hold; a name added to one is added here too, deliberately.
NAMES = {
    "t2_agentic_voice.ports": {
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
    },
    "t2_agentic_voice.groq": {"GroqChat", "GroqSTT", "GroqTTS"},
    "t2_agentic_voice.classifiers": {"EcapaLanguage", "SileroLanguage"},
    "t2_agentic_voice.identity": {"DevIdentity", "SignedJoinTokens"},
    "t2_agentic_voice.server": {"combine_lifespans", "serve"},
    "t2_agentic_voice.stores": {
        "ClauseCache",
        "ClauseCounts",
        "MemoryOutbox",
        "MemoryUsedTokens",
        "PhraseCache",
        "SqliteOutbox",
        "SqliteUsedTokens",
    },
    "t2_agentic_voice.events": {
        "ActionCompleted",
        "ActionUnconfirmed",
        "AgentSpeechEnded",
        "CallEnded",
        "CallReport",
        "CallStarted",
        "ClientConnection",
        "ConfirmationAnswered",
        "ConfirmationRequested",
        "Event",
        "GuardBlocked",
        "Interrupted",
        "ModelUsage",
        "ProviderFailed",
        "ToolFinished",
        "ToolStarted",
        "TransportFailed",
        "TurnMetrics",
        "TurnRecord",
        "TurnTimes",
        "UserTurnEnded",
    },
    "t2_agentic_voice.languages": {
        "Kept",
        "Pronunciations",
        "SpellingIssue",
        "SpellingRule",
        "WhisperPrompt",
        "normalize_arabic",
        "normalize_digits",
        "pronounce",
        "provider_text",
        "register_of",
        "remove_stray_script",
        "speak_id",
        "speak_number",
        "spelling_issues",
        "split_clauses",
        "whisper_prompt",
    },
    "t2_agentic_voice.evals": {
        "ActionSafetySuite",
        "AudioCall",
        "BlockedClause",
        "EchoTiming",
        "FakeKnowledgeBase",
        "FunctionLLM",
        "HeardClause",
        "KnowledgeSearch",
        "LanguageChoice",
        "LanguageTurn",
        "OverlapReplay",
        "OverlapRequest",
        "Pause",
        "PhraseAudio",
        "Recall",
        "ScriptExhaustedError",
        "ScriptStep",
        "ScriptedLLM",
        "TextCall",
        "TextToolCall",
        "TextTurn",
        "TurnEnd",
        "TurnExpectations",
        "TurnReplay",
        "TurnTiming",
        "cer",
        "chosen",
        "consent_check_answer",
        "consent_check_request",
        "echo_timings",
        "id_recall",
        "is_consent_check",
        "sign_test",
        "silence_output",
        "term_recall",
        "turn_ends",
        "turn_languages",
        "uncertain_overlap_answer",
        "uncertain_overlap_request",
        "wer",
    },
    "t2_agentic_voice.tracing": {"Redactor", "SpeechToTextSpan", "Tracing"},
}
# The package root's names, the same way. Status, status, NotFoundError and InvalidRequestError
# are in no row of the design's 5.1 (TD-034). VoiceSettings's groups (and TtsVoice, the value of
# its `tts.languages`) and StructuredLogger, which `get_logger` returns, are public because public
# signatures name them (D-032; test_public_types.py), beside VoiceSettings and get_logger. Plan
# 006 adds the talker's: the tools (`Tool`, `tool`, `from_caller` and `FromCaller`, `CallContext`,
# `ToolResult`, `ToolError`, `knowledge_tool`), the declaration's parts (`Vocabulary`, and
# `DeclaredTool`, the shape `VoiceAgent.tools` holds), `Card`, `render_prompt`, and the `llm` and
# `guard` groups' classes. Plan 007 adds the actions: `action`, `Action`, what it is told
# (`ActionContext`, `HeardConsent`, `RecordedAction`, `ConversationLine`), the words of its
# declaration (`Say`, `ReadBack`, `Claims`, `Spoken`), and `ActionRejected` and `ActionNotSent`.
# Plan 010 adds the key groups of the providers measured beside Groq (D-100).
ROOT_NAMES = {
    "TelnyxSettings",
    "NabrahSettings",
    "HumainSettings",
    "Action",
    "ActionContext",
    "ActionNotSent",
    "ActionRejected",
    "CallContext",
    "Caller",
    "Card",
    "Claims",
    "CohereSettings",
    "ConfigurationError",
    "Consent",
    "ConversationLine",
    "DeclaredTool",
    "ElevenLabsSettings",
    "FromCaller",
    "GroqSettings",
    "GuardSettings",
    "HeardConsent",
    "InterruptionSettings",
    "InvalidRequestError",
    "InworldSettings",
    "JoinRejected",
    "JoinSettings",
    "Language",
    "LimitSettings",
    "LlmSettings",
    "LoggingSettings",
    "NotFoundError",
    "OpenAISettings",
    "Phrases",
    "PrivacySettings",
    "ProviderError",
    "Providers",
    "ReadBack",
    "RecordedAction",
    "Say",
    "ServerSettings",
    "SessionSettings",
    "SonioxSettings",
    "SpeechmaticsSettings",
    "Spoken",
    "Status",
    "StorageSettings",
    "StructuredLogger",
    "SttSettings",
    "T2VoiceError",
    "Tool",
    "ToolError",
    "ToolResult",
    "TracingSettings",
    "TtsSettings",
    "TtsVoice",
    "TurnSettings",
    "Vocabulary",
    "VoiceAgent",
    "VoiceRuntime",
    "VoiceSettings",
    "WordSettings",
    "Words",
    "action",
    "configure_logging",
    "from_caller",
    "get_logger",
    "knowledge_tool",
    "render_prompt",
    "status",
    "tool",
}


def test_every_facade_is_listed_here() -> None:
    assert set(load_config(ROOT).arch.facades) == set(NAMES)


@pytest.mark.parametrize("facade", sorted(NAMES))
def test_a_facade_re_exports_its_names_from_the_layers(facade: str) -> None:
    module = importlib.import_module(facade)
    assert set(module.__all__) == NAMES[facade]
    for name in module.__all__:
        home = getattr(module, name).__module__
        assert home.startswith("t2_agentic_voice.") and home != facade, (name, home)


def test_the_package_root_re_exports_its_names_from_the_layers() -> None:
    assert set(t2_agentic_voice.__all__) == ROOT_NAMES
    for name in t2_agentic_voice.__all__:
        home = getattr(t2_agentic_voice, name).__module__
        assert home.startswith("t2_agentic_voice.") and home not in NAMES, (name, home)
