"""Groq's Orpheus behind the text-to-speech port (the design's 6.1; D-004).

Built by plan 003's Track B; until then a stub. It speaks each language in the model and voice
`tts.languages` gives it (`canopylabs/orpheus-arabic-saudi` and `canopylabs/orpheus-v1-english`),
one request per clause with `response_format` "wav" passed explicitly, the request's fields as
Block 0's baseline records them (tests/t2_agentic_voice/fixtures/groq_tts_request.json). It
builds its client as every Groq adapter does (`adapters/groq_client.py`: the key, base URL and
timeout always passed, the SDK's retries off, every request with the adapter's own headers, a
body that does not open as its JSON does refused unsent, `groq` imported with `GROQ_LOG`
undone). It refuses a text over the model's `max_chars` (200 for both models); reads the sample
rate from each WAV's header, never assumes it; trims the silence before the speech only with
`tts.trim_silence` on; flags a take that came back cut short on its last chunk; puts each
response's `x-ratelimit-remaining-requests` and `x-ratelimit-remaining-tokens` on its first
chunk; and raises `ProviderError` for every failure, a model whose terms are not accepted
`rejected` with a FIX line that names the console's terms. A cancel stops it within 50 ms,
leaving no task or connection. No public signature names a `groq` type (the design's 5.3).
Public through the `groq` facade (D-021).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import httpx
from pydantic import SecretStr

from t2_agentic_voice.adapters.groq_client import DATA_FLOW
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

_STUB = "GroqTTS is built by plan 003's Track B"


class GroqTTS:
    """Text-to-speech with Groq's Orpheus models, a model and a voice per language; a
    `TextToSpeech`. `transport` replaces the HTTP transport (a test's fake one); by default the
    adapter talks to `base_url` over its own connection pool. Close it with `aclose()`."""

    name: str = "groq"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        languages: Mapping[LanguageTag, TtsVoice],
        base_url: str,
        timeout_s: float,
        trim_silence: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """The adapter for these values, which it refuses as the settings would (GP-20), each
        error naming the setting and never the value."""
        raise NotImplementedError(_STUB)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> GroqTTS:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url`,
        `tts.languages`, `tts.timeout_s` and `tts.trim_silence`. ConfigurationError naming
        `T2V_GROQ__API_KEY` (under the settings' prefix) when no key is set, as `GroqSTT`'s."""
        raise NotImplementedError(_STUB)

    def max_chars(self, language: str) -> int | None:
        """The longest text one request of `language` takes (the port's `max_chars`)."""
        raise NotImplementedError(_STUB)

    def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` spoken in `language`'s model and voice, chunk by chunk as Groq streams it (the
        port's `synthesize`)."""
        raise NotImplementedError(_STUB)

    async def check_language(self, language: str) -> None:
        """Return when `language` has a model and a voice and Groq lists the model, with no
        synthesis (the port's `check_language`)."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        raise NotImplementedError(_STUB)
