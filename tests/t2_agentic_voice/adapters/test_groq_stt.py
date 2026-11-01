"""GroqSTT. Plan 002's Track B builds it and replaces this file's stub test with its own (its
request against the baseline in tests/t2_agentic_voice/fixtures/groq_stt_request.json)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip


def test_groq_stt_is_a_stub_until_track_b(settings: Settings) -> None:
    with pytest.raises(NotImplementedError, match="Track B"):
        GroqSTT(
            api_key=SecretStr("made-up-key"),
            model="whisper-large-v3",
            base_url="https://api.groq.com",
            timeout_s=6.0,
        )
    with pytest.raises(NotImplementedError, match="Track B"):
        GroqSTT.from_settings(settings)
    stub = GroqSTT.__new__(GroqSTT)  # the methods' stubs, past the constructor's
    with pytest.raises(NotImplementedError, match="Track B"):
        asyncio.run(stub.transcribe(AudioClip(pcm16=b""), language="ar", prompt=None))
    with pytest.raises(NotImplementedError, match="Track B"):
        asyncio.run(stub.aclose())
