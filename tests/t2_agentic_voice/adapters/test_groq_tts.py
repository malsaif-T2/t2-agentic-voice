"""GroqTTS. Plan 003's Track B builds it and replaces this file's stub test with its own (its
request against Block 0's baseline in tests/t2_agentic_voice/fixtures/groq_tts_request.json)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_tts import GroqTTS
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech


def test_groq_tts_is_a_stub_until_track_b(settings: VoiceSettings) -> None:
    with pytest.raises(NotImplementedError, match="Track B"):
        GroqTTS(
            api_key=SecretStr("made-up-key"),
            languages=TtsSettings().languages,
            base_url="https://api.groq.com",
            timeout_s=6.0,
        )
    with pytest.raises(NotImplementedError, match="Track B"):
        GroqTTS.from_settings(settings)
    stub = GroqTTS.__new__(GroqTTS)  # the methods' stubs, past the constructor's
    port: TextToSpeech = stub  # mypy checks the port's shape
    assert (port.name, port.data_flow.provider) == ("groq", "Groq")
    calls: list[Callable[[], object]] = [
        lambda: stub.max_chars("en"),
        lambda: stub.synthesize("made-up words", language="en"),
        lambda: asyncio.run(stub.check_language("en")),
        lambda: asyncio.run(stub.aclose()),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track B"):
            call()
