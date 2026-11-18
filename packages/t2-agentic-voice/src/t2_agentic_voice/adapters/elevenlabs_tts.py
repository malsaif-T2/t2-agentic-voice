"""ElevenLabs' voices behind the text-to-speech port (D-114: measured beside Groq, not a default).

`ElevenLabsTTS` speaks each language in the model and voice `tts.languages` gives it under
`tts.provider = "elevenlabs"` (core/settings/tts_voices.py: the model an ElevenLabs model ID,
the voice a voice ID), one request per clause, by raw HTTPS (adapters/provider_http.py: no SDK,
no variable of its own read, no redirect followed):

- **Streaming.** `POST /v1/text-to-speech/{voice_id}/stream?output_format=pcm_24000`, whose
  answer is raw mono 16-bit little-endian PCM at 24 kHz, streamed as it is made, so the first
  sound plays before the take has ended; each piece is a chunk as soon as it holds whole samples
  (adapters/pcm_takes.py). `tts.timeout_s` bounds each step of the request, the connection and
  each read of the answer, not the whole take, as the Groq adapter's.
- **The body**: the text, the `model_id`, and the clause's `language_code` (`ar` or `en`), which
  every model listed takes (probed 2026-11-17), so the model and its text normalization keep to
  the clause's language; the voice's own settings, as its owner saved them, are not overridden.
- **Headroom**: ElevenLabs reports its concurrency on each answer (`current-concurrent-requests`
  and `maximum-concurrent-requests`), whose difference is the first chunk's
  `remaining_requests`; it reports no tokens.
- **check_language**: `GET /v1/models`, which costs nothing, so a model the key cannot use is
  `rejected` before a call; its `Date` header is the answer's time. The voice shows only at its
  first synthesis: a key restricted to text-to-speech (no `voices_read`, as the owner's) cannot
  read a voice.
- **Its socket** (D-121): it is a `StreamingTextToSpeech` too. A language whose model is one of
  the dialogue models (`eleven_v3*`, `eleven_v4*`) `streams`, and `open_stream` opens one call's
  session on the Text-to-Dialogue socket (adapters/elevenlabs_stream.py), with the same key,
  voices, timeout and silence trim.

Every failure is a ProviderError naming no key or text; a cancel stops the request at once,
closing its response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, TypeAdapter

from t2_agentic_voice.adapters.elevenlabs_stream import (
    DIALOGUE_URL,
    DialogueStream,
    on_dialogue_socket,
    open_dialogue,
)
from t2_agentic_voice.adapters.groq_client import server_time
from t2_agentic_voice.adapters.pcm_takes import PcmTake, no_voice, too_long
from t2_agentic_voice.adapters.provider_http import (
    TTS_INSTEAD,
    given_key,
    http_client,
    http_failure,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.provider_socket import Opener
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.provider_keys import ElevenLabsSettings
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

VENDOR: Final = "ElevenLabs"
BASE_URL: Final = "https://api.elevenlabs.io"
RATE: Final = 24_000
OUTPUT_FORMAT: Final = f"pcm_{RATE}"
# The longest text one request of each model takes, in characters, as its model list gives it
# (`max_characters_request_subscribed_user`, read 2026-11-17).
MAX_CHARS: Final[Mapping[str, int]] = {
    "eleven_flash_v2_5": 40_000,
    "eleven_turbo_v2_5": 40_000,
    "eleven_multilingual_v2": 10_000,
    "eleven_v3": 5_000,
    "eleven_v3_conversational": 5_000,
    "eleven_v4": 10_000,
    "eleven_v4_turbo": 10_000,
}
_CONCURRENCY: Final = ("current-concurrent-requests", "maximum-concurrent-requests")
# Where ElevenLabs processes and keeps text-to-speech requests (its data pages, D-114).
DATA_FLOW: Final = DataFlow(
    provider="ElevenLabs",
    processed_in="US (no Saudi region; EU and India residency on Enterprise only)",
    stored_in="not stated by the provider for text-to-speech requests beyond its history",
    retention=(
        "kept in the account's history unless zero retention (Enterprise) is on; used to "
        "improve its models unless that is turned off"
    ),
)


class ElevenLabsTTS:
    """Text-to-speech with ElevenLabs, a model and a voice per language; a `TextToSpeech` and a
    `StreamingTextToSpeech`. `transport` replaces the HTTP transport and `opener` the socket's
    connection (a test's fakes). Close it with `aclose()`."""

    name: str = "elevenlabs"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        languages: Mapping[LanguageTag, TtsVoice],
        timeout_s: float,
        trim_silence: bool = False,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: Opener = open_dialogue,
    ) -> None:
        self._api_key = given_key(api_key, ElevenLabsSettings, VENDOR, instead=TTS_INSTEAD)
        self._languages: dict[str, TtsVoice] = dict(languages.items())
        self._base = base_url.rstrip("/")
        self._timeout_s, self._trim = timeout_s, trim_silence
        self._http = http_client(timeout_s=timeout_s, transport=transport)
        self._open = opener

    @classmethod
    def from_settings(
        cls,
        settings: VoiceSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: Opener = open_dialogue,
    ) -> ElevenLabsTTS:
        """The adapter the settings describe: `elevenlabs`' key, `tts.languages`,
        `tts.timeout_s` and `tts.trim_silence`; a ConfigurationError naming
        `T2V_ELEVENLABS__API_KEY` (under the settings' prefix) when no key is set."""
        key = provider_key(settings, settings.elevenlabs, VENDOR, instead=TTS_INSTEAD)
        tts = settings.tts
        return cls(
            api_key=key,
            languages=tts.languages,
            timeout_s=tts.timeout_s,
            trim_silence=tts.trim_silence,
            transport=transport,
            opener=opener,
        )

    def __repr__(self) -> str:
        voices = {tag: f"{v.model}:{v.voice}" for tag, v in self._languages.items()}
        return f"ElevenLabsTTS(languages={voices!r}, timeout_s={self._timeout_s!r})"

    def max_chars(self, language: str) -> int | None:
        """The longest text one request of `language` takes: its model's; for a language with
        no model, the least of them."""
        voice = self._languages.get(language)
        return MAX_CHARS.get(voice.model) if voice else min(MAX_CHARS.values())

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` spoken in `language`'s model and voice, chunk by chunk as ElevenLabs streams
        it (the port's `synthesize`; the module's docstring)."""
        voice = self._languages.get(language)
        if voice is None:
            raise no_voice()
        limit = MAX_CHARS.get(voice.model)
        if limit is not None and len(text) > limit:
            raise too_long(limit)
        body: dict[str, JsonValue] = {
            "text": text,
            "model_id": voice.model,
            "language_code": primary_code(language),
        }
        take = PcmTake(rate=RATE, trim=self._trim)
        url = f"{self._base}/v1/text-to-speech/{voice.voice}/stream"
        headroom: int | None = None
        problem: ProviderError | None = None
        try:
            async with self._http.stream(
                "POST",
                url,
                params={"output_format": OUTPUT_FORMAT},
                json=body,
                headers=self._headers(),
            ) as response:
                ok_status(response)
                headroom = _headroom(response.headers)
                async for data in response.aiter_bytes():
                    chunk = take.feed(data)
                    if chunk is not None:
                        first = take.sent == 1
                        yield chunk.model_copy(
                            update={"remaining_requests": headroom if first else None}
                        )
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            problem = http_failure(self.name, error)
        if problem is not None:
            raise problem from None
        last = take.last(text, language)
        if last is not None:
            first = not take.sent
            yield last.model_copy(update={"remaining_requests": headroom if first else None})

    def streams(self, language: str) -> bool:
        """Whether `language`'s model speaks on the Text-to-Dialogue socket."""
        voice = self._languages.get(language)
        return voice is not None and on_dialogue_socket(voice.model)

    def open_stream(self, *, language: str) -> DialogueStream:
        """One call's session on the socket, opening for `language` (the module's docstring)."""
        return DialogueStream(
            api_key=self._api_key,
            voices=self._languages,
            language=language,
            timeout_s=self._timeout_s,
            trim_silence=self._trim,
            url=DIALOGUE_URL,
            opener=self._open,
        )

    async def check_language(self, language: str) -> datetime | None:
        """Return when `language` has a model and a voice and ElevenLabs lists the model for the
        key, with no synthesis (the port's `check_language`): one GET of the model list, which
        costs nothing; its time from the answer's `Date` header. ConfigurationError for a
        language with no model or voice; ProviderError (`rejected`) for a model the list leaves
        out, and for every failure."""
        voice = self._languages.get(language)
        if voice is None:
            setting = setting_name("tts", "languages")
            raise ConfigurationError(
                f"No text-to-speech model or voice is set for the language {language!r}. FIX: "
                f"give {setting} a model and a voice for it.",
                details={"setting": setting},
            )
        try:
            response = ok_status(
                await self._http.get(f"{self._base}/v1/models", headers=self._headers())
            )
            listed = _Listing.validate_json(response.content)
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            problem = http_failure(self.name, error)
        else:
            if voice.model in {model.model_id for model in listed}:
                return server_time(response.headers)
            details: dict[str, JsonValue] = {"error": "model_not_listed", "model": voice.model}
            problem = ProviderError("rejected", False, details=details)
        raise problem from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key.get_secret_value()}


def _headroom(headers: httpx.Headers) -> int | None:
    """The requests ElevenLabs still allows at once: its maximum less those running, else None."""
    values = [headers.get(name, "") for name in _CONCURRENCY]
    if not all(value.isascii() and value.isdigit() for value in values):
        return None
    current, most = (int(value) for value in values)
    return max(0, most - current)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    model_id: str


# ElevenLabs' model list, as far as the adapter reads it: each model's ID.
_Listing: Final = TypeAdapter(list[_Model])
