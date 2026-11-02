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
        "DataFlow",
        "IdentityVerifier",
        "JoinContext",
        "SpeechToText",
        "TextToSpeech",
        "Transcript",
        "UsedTokens",
    },
    "t2_agentic_voice.groq": {"GroqSTT", "GroqTTS"},
    "t2_agentic_voice.identity": {"DevIdentity", "SignedJoinTokens"},
    "t2_agentic_voice.server": {"combine_lifespans", "serve"},
    "t2_agentic_voice.stores": {"MemoryUsedTokens", "SqliteUsedTokens"},
    "t2_agentic_voice.events": {
        "AgentSpeechEnded",
        "CallEnded",
        "CallReport",
        "CallStarted",
        "ClientConnection",
        "Event",
        "Interrupted",
        "ModelUsage",
        "ProviderFailed",
        "TransportFailed",
        "TurnMetrics",
        "TurnRecord",
        "TurnTimes",
        "UserTurnEnded",
    },
    "t2_agentic_voice.languages": {
        "SpellingIssue",
        "SpellingRule",
        "normalize_arabic",
        "normalize_digits",
        "speak_id",
        "speak_number",
        "spelling_issues",
    },
    "t2_agentic_voice.evals": {
        "EchoTiming",
        "Recall",
        "TurnEnd",
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
# are in no row of the design's 5.1 (TD-034).
ROOT_NAMES = {
    "Caller",
    "ConfigurationError",
    "Consent",
    "InvalidRequestError",
    "JoinRejected",
    "Language",
    "NotFoundError",
    "ProviderError",
    "Providers",
    "Status",
    "T2VoiceError",
    "VoiceAgent",
    "VoiceRuntime",
    "VoiceSettings",
    "configure_logging",
    "get_logger",
    "status",
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
