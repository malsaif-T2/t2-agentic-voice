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
    "t2_agentic_voice.identity": {"DevIdentity", "SignedJoinTokens"},
    "t2_agentic_voice.server": {"combine_lifespans", "serve"},
    "t2_agentic_voice.stores": {"MemoryUsedTokens", "PhraseCache", "SqliteUsedTokens"},
    "t2_agentic_voice.events": {
        "AgentSpeechEnded",
        "CallEnded",
        "CallReport",
        "CallStarted",
        "ClientConnection",
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
        "Pronunciations",
        "SpellingIssue",
        "SpellingRule",
        "normalize_arabic",
        "normalize_digits",
        "pronounce",
        "provider_text",
        "speak_id",
        "speak_number",
        "spelling_issues",
        "split_clauses",
    },
    "t2_agentic_voice.evals": {
        "AudioCall",
        "BlockedClause",
        "EchoTiming",
        "FakeKnowledgeBase",
        "FunctionLLM",
        "HeardClause",
        "KnowledgeSearch",
        "OverlapReplay",
        "OverlapRequest",
        "PhraseAudio",
        "Recall",
        "ScriptedLLM",
        "TextCall",
        "TextToolCall",
        "TextTurn",
        "TurnEnd",
        "TurnExpectations",
        "TurnTiming",
        "cer",
        "echo_timings",
        "id_recall",
        "sign_test",
        "silence_output",
        "term_recall",
        "turn_ends",
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
# `guard` groups' classes.
ROOT_NAMES = {
    "CallContext",
    "Caller",
    "Card",
    "ConfigurationError",
    "Consent",
    "DeclaredTool",
    "FromCaller",
    "GroqSettings",
    "GuardSettings",
    "InterruptionSettings",
    "InvalidRequestError",
    "JoinRejected",
    "JoinSettings",
    "Language",
    "LimitSettings",
    "LlmSettings",
    "LoggingSettings",
    "NotFoundError",
    "Phrases",
    "PrivacySettings",
    "ProviderError",
    "Providers",
    "ServerSettings",
    "SessionSettings",
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
    "VoiceAgent",
    "VoiceRuntime",
    "Vocabulary",
    "VoiceSettings",
    "WordSettings",
    "Words",
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
