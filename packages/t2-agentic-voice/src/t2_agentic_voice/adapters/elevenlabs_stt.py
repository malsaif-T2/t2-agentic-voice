"""ElevenLabs' Scribe behind the speech-to-text port (D-100: measured beside Groq, not a default).

`ElevenLabsSTT` sends one clip, wrapped as WAV, to ElevenLabs' batch speech-to-text endpoint
(`POST /v1/speech-to-text`, multipart) by raw HTTPS (adapters/provider_http.py: no SDK, no
variable of its own read, no redirect followed), with:

- `model_id`, `scribe_v3` by default; the language the request names as `language_code`, none
  to let Scribe detect it; audio events and timestamps off, since only the text is read.
- `keyterms`: the terms of the prompt the call sends (the agent's vocabulary, then the command
  words; domain/whisper_prompt.py), at most 100, each at most 50 characters: ElevenLabs bills a
  20-second minimum a request past 100 keyterms (the provider guide, read 2026-11-16).
- The answer's `language_code` and `language_probability` ride on the `Transcript` as
  `heard_language` (ElevenLabs' ISO 639-3 codes `ara` and `eng` mapped to `ar` and `en`) and
  `language_probability`, so the language switch can read them; `language` is the request's
  when it named one, else the one heard.

`warm_up()` (the `WarmUp` port, domain/ports/connection_warmth.py) opens the adapter's
connection with a GET of ElevenLabs' model list (`GET /v1/models`), which costs nothing, as a
call joins; a refused answer still leaves the connection open.

Its output is data, never an instruction (docs/SECURITY.md, trust boundaries). Every failure is
a ProviderError naming no key, audio or transcript; a cancel stops the request at once.
"""

from __future__ import annotations

import asyncio
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from t2_agentic_voice.adapters.provider_http import (
    given_key,
    http_client,
    http_failure,
    keyterms,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.wav_files import wav_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.provider_keys import ElevenLabsSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "ElevenLabs"
BASE_URL: Final = "https://api.elevenlabs.io"
MODEL: Final = "scribe_v3"
# The most keyterms a request carries, and the longest one, in characters (the module's docstring).
MOST_KEYTERMS: Final = 100
LONGEST_KEYTERM: Final = 50
# ElevenLabs' three-letter codes for the agent's languages, as the agent writes them.
_CODES: Final = {"ara": "ar", "eng": "en"}
# Where ElevenLabs processes and keeps speech-to-text requests, from the provider guide's reading
# of its data pages (2026-11-16).
DATA_FLOW: Final = DataFlow(
    provider="ElevenLabs",
    processed_in="US (no Saudi region)",
    stored_in="not stated by the provider for speech-to-text requests",
    retention=(
        "used to improve its models unless 'Improve the models for everyone' is turned off "
        "(Data use), which covers only audio sent after; zero retention on Enterprise only"
    ),
)


class ElevenLabsSTT:
    """Speech-to-text with ElevenLabs' Scribe (`model`, `scribe_v3` by default); a
    `SpeechToText` and a `WarmUp`. `transport` replaces the HTTP transport (a test's fake one).
    Close it with `aclose()`."""

    name: str = "elevenlabs"
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
        self._api_key = given_key(api_key, ElevenLabsSettings, VENDOR)
        self._model = model
        self._url = f"{base_url.rstrip('/')}/v1/speech-to-text"
        self._models_url = f"{base_url.rstrip('/')}/v1/models"
        self._timeout_s = timeout_s
        self._http = http_client(timeout_s=timeout_s, transport=transport)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> ElevenLabsSTT:
        """The adapter the settings describe: `elevenlabs`' key and `stt.timeout_s`; a
        ConfigurationError naming `T2V_ELEVENLABS__API_KEY` (under the settings' prefix) when no
        key is set."""
        key = provider_key(settings, settings.elevenlabs, VENDOR)
        return cls(api_key=key, timeout_s=settings.stt.timeout_s, transport=transport)

    def __repr__(self) -> str:
        return f"ElevenLabsSTT(model={self._model!r}, timeout_s={self._timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring). The whole
        request, sent once, takes at most `timeout_s`. Raises ProviderError on every failure,
        an answer it cannot read included."""
        fields: dict[str, str | list[str]] = {
            "model_id": self._model,
            "tag_audio_events": "false",
            "timestamps_granularity": "none",
        }
        if language:
            fields["language_code"] = language
        terms = keyterms(prompt, most=MOST_KEYTERMS, longest=LONGEST_KEYTERM)
        if terms:
            fields["keyterms"] = list(terms)
        headers = {"xi-api-key": self._api_key.get_secret_value(), "accept": "application/json"}
        files = {"file": ("speech.wav", wav_of(clip), "audio/wav")}
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._http.post(
                    self._url, data=fields, files=files, headers=headers
                )
            answer = _Answer.model_validate_json(ok_status(response).content)
            transcript = answer.transcript(language or None, billed_seconds=clip.seconds)
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            provider_error = http_failure(self.name, error)
        else:
            return transcript
        raise provider_error from None

    async def warm_up(self) -> None:
        """Open the adapter's connection with `GET /v1/models`, which costs nothing (the
        `WarmUp` port), within `timeout_s`. ProviderError on its failure."""
        headers = {"xi-api-key": self._api_key.get_secret_value(), "accept": "application/json"}
        try:
            async with asyncio.timeout(self._timeout_s):
                ok_status(await self._http.get(self._models_url, headers=headers))
        except Exception as error:  # every failure, httpx's; never a cancel
            provider_error = http_failure(self.name, error)
        else:
            return
        raise provider_error from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._http.aclose()


class _Answer(BaseModel):
    """ElevenLabs' answer, as far as the adapter reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    text: str
    language_code: str | None = None
    language_probability: float | None = Field(default=None, ge=0, le=1)

    def transcript(self, language: str | None, *, billed_seconds: float) -> Transcript:
        heard = _CODES.get(self.language_code or "", self.language_code or None)
        return Transcript(
            text=self.text.strip(),
            language=language or heard,
            heard_language=heard,
            language_probability=self.language_probability,
            billed_seconds=billed_seconds,
        )
