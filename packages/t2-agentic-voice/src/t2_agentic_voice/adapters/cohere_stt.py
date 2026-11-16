"""Cohere's Transcribe Arabic behind the speech-to-text port (D-100: measured beside Groq, not a
default).

`CohereSTT` sends one clip, wrapped as WAV, to Cohere's batch transcription endpoint
(`POST /v2/audio/transcriptions`, multipart) by raw HTTPS (adapters/provider_http.py: no SDK, no
variable of its own read, no redirect followed), with:

- `model`, `cohere-transcribe-arabic-07-2026` by default.
- `language`: the model detects none, so a language is always named: the request's, or
  `DEFAULT_LANGUAGE` (Arabic, the model's own) when the request names none. An English call names
  `en`; an Arabic call names `ar` for its mixed turns too.
- No prompt and no keyterms: the endpoint takes neither.

Cohere gives no language label or score, so the transcript's `heard_language` and
`language_probability` stay None; `language` is the one the request named, and None when it
named none: the Arabic sent then is no language heard, so a request naming none (Whisper's
detection under `stt.live_language = "detected"`) never reads as the caller speaking Arabic and
moves no call. Its trial key allows 5 requests a
minute (the provider guide, read 2026-11-16): a 429 is a `rate_limited` ProviderError with its
`retry-after`, which the caller paces to. Its output is data, never an instruction
(docs/SECURITY.md, trust boundaries). Every failure is a ProviderError naming no key, audio or
transcript; a cancel stops the request at once.
"""

from __future__ import annotations

import asyncio
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from t2_agentic_voice.adapters.provider_http import (
    given_key,
    http_client,
    http_failure,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.wav_files import wav_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.provider_keys import CohereSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "Cohere"
BASE_URL: Final = "https://api.cohere.com"
MODEL: Final = "cohere-transcribe-arabic-07-2026"
# The language sent when the request names none: the model detects no language.
DEFAULT_LANGUAGE: Final = "ar"
# Where Cohere processes and keeps transcription requests, from the provider guide's reading of
# its data pages (2026-11-16).
DATA_FLOW: Final = DataFlow(
    provider="Cohere",
    processed_in="not confirmed by the provider (no region stated for the trial key)",
    stored_in="its request logs",
    retention=(
        "logs deleted after 30 days; used for training unless Data Controls' toggle is set to "
        "Off; zero retention on enterprise plans only"
    ),
)


class CohereSTT:
    """Speech-to-text with Cohere's Transcribe Arabic (`model`); a `SpeechToText`. `transport`
    replaces the HTTP transport (a test's fake one). Close it with `aclose()`."""

    name: str = "cohere"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        timeout_s: float,
        model: str = MODEL,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = given_key(api_key, CohereSettings, VENDOR)
        self._model = model
        self._url = f"{base_url.rstrip('/')}/v2/audio/transcriptions"
        self._timeout_s = timeout_s
        self._http = http_client(timeout_s=timeout_s, transport=transport)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> CohereSTT:
        """The adapter the settings describe: `cohere`'s key and `stt.timeout_s`; a
        ConfigurationError naming `T2V_COHERE__API_KEY` (under the settings' prefix) when no key
        is set."""
        key = provider_key(settings, settings.cohere, VENDOR)
        return cls(api_key=key, timeout_s=settings.stt.timeout_s, transport=transport)

    def __repr__(self) -> str:
        return f"CohereSTT(model={self._model!r}, timeout_s={self._timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring), in
        `language` or `DEFAULT_LANGUAGE`, the transcript naming `language` (None for none);
        `prompt` is not sent. The whole request, sent once,
        takes at most `timeout_s`. Raises ProviderError on every failure, an answer it cannot
        read included."""
        sent = language or DEFAULT_LANGUAGE
        fields = {"model": self._model, "language": sent}
        headers = {
            "authorization": f"Bearer {self._api_key.get_secret_value()}",
            "accept": "application/json",
        }
        files = {"file": ("speech.wav", wav_of(clip), "audio/wav")}
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._http.post(
                    self._url, data=fields, files=files, headers=headers
                )
            text = _Answer.model_validate_json(ok_status(response).content).text
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            provider_error = http_failure(self.name, error)
        else:
            return Transcript(text=text.strip(), language=language, billed_seconds=clip.seconds)
        raise provider_error from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._http.aclose()


class _Answer(BaseModel):
    """Cohere's answer, as far as the adapter reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    text: str
