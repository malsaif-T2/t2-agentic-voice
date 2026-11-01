"""Groq's Whisper behind the speech-to-text port (the design's 6.1; D-004).

Built by plan 002's Track B; until then a stub. It transcribes with the model `stt.model`
names, always passes the key, `groq.base_url` and the timeout to the SDK (so the SDK never falls
back to its own environment variables), turns the SDK's own retries off, raises `ProviderError`
on every failure, and names no `groq` type in a public signature (the design's 5.3). Public
through the `groq` facade (D-021).
"""

from __future__ import annotations

from pydantic import SecretStr

from t2_agentic_voice.core.config import Settings, SttModel
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

_STUB = "GroqSTT is built by plan 002's Track B"


class GroqSTT:
    """Speech-to-text with Groq's `whisper-large-v3` or `whisper-large-v3-turbo`; a
    `SpeechToText`."""

    name: str
    data_flow: DataFlow

    def __init__(
        self, *, api_key: SecretStr, model: SttModel, base_url: str, timeout_s: float
    ) -> None:
        raise NotImplementedError(_STUB)

    @classmethod
    def from_settings(cls, settings: Settings) -> GroqSTT:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url`,
        `stt.model` and `stt.timeout_s`. ConfigurationError naming `T2V_GROQ__API_KEY` when no
        key is set."""
        raise NotImplementedError(_STUB)

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`)."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        raise NotImplementedError(_STUB)
