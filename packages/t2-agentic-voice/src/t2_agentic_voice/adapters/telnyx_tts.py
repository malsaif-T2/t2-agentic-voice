"""Telnyx's voices behind the text-to-speech port (D-114: measured beside Groq, not a default).

`TelnyxTTS` speaks each language in the voice `tts.languages` gives it under
`tts.provider = "telnyx"` (core/settings/tts_voices.py: the model the voice's family, such as
`Telnyx.Bayan`, Telnyx's Arabic model of 13 dialects and English, and the voice its speaker,
joined by a dot as Telnyx names its voices: `Telnyx.Bayan.Fahd`), one clause per connection:

- **Streaming.** Telnyx's text-to-speech WebSocket (`wss://api.telnyx.com/v2/text-to-speech/
  speech?voice=...&audio_format=linear16&sample_rate=16000`), opened by
  adapters/provider_socket.py's `open_socket` (no proxy, no keepalive, a logger that logs
  nothing); it sends `{"text": " "}`, the clause, then `{"text": ""}`, which ends the take, and
  reads each frame's base64 audio, raw mono 16-bit little-endian PCM at Bayan's own 16 kHz, as a
  chunk as soon as it holds whole samples (adapters/pcm_takes.py), until the frame that says
  `isFinal`, or Telnyx's orderly close. Its REST answer comes whole, so the first sound would
  wait for the take's end (probed 2026-11-17). `tts.timeout_s` bounds the handshake and each
  wait for a frame, not the whole take.
- **Its cache**: Telnyx keeps the takes it made and answers the same voice and text from them
  (`cached` on each frame); the adapter leaves it on, so a fixed line is cheaper and faster.
- **check_language**: `GET /v2/text-to-speech/voices`, of the voice's own provider at Telnyx,
  which costs nothing: a voice it does not list is `rejected`; its `Date` header is the time.

The key goes as a bearer token in the handshake's and the request's header. An error frame is a
`server_error` worth asking again for (Telnyx sent one now and then for a clause it spoke on the
next try, 2026-11-17); a frame that is not Telnyx's, and every other failure, a ProviderError as
the socket helper maps it; none names the key or the text. A cancel stops the take at once,
closing its socket.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Final
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, ValidationError
from websockets.exceptions import ConnectionClosedOK

from t2_agentic_voice.adapters.groq_client import server_time
from t2_agentic_voice.adapters.pcm_takes import PcmTake, no_voice
from t2_agentic_voice.adapters.provider_http import (
    TTS_INSTEAD,
    AnswerError,
    given_key,
    http_client,
    http_failure,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.provider_socket import (
    Message,
    Opener,
    Socket,
    close_quietly,
    open_socket,
    socket_failure,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.provider_keys import TelnyxSettings
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

VENDOR: Final = "Telnyx"
STREAM_URL: Final = "wss://api.telnyx.com/v2/text-to-speech/speech"
VOICES_URL: Final = "https://api.telnyx.com/v2/text-to-speech/voices"
RATE: Final = 16_000  # Bayan's own rate; a higher one is only resampled (Telnyx's Bayan page)
# The provider Telnyx files each voice family under, as its voices list names it.
LISTED_AS: Final[Mapping[str, str]] = {"Telnyx.Bayan": "telnyx", "Humain": "humain"}
# Where Telnyx processes and keeps text-to-speech requests, as far as its pages say (D-114).
DATA_FLOW: Final = DataFlow(
    provider="Telnyx",
    processed_in=(
        "Telnyx's network (US-based; licensed in the UAE and Saudi Arabia, GPUs in Dubai); no "
        "in-Kingdom processing documented"
    ),
    stored_in="Telnyx's text-to-speech cache, for the takes it made (its `cached` frames)",
    retention="not stated; Telnyx trains on no input without the customer's written opt-in",
)


class TelnyxTTS:
    """Text-to-speech through Telnyx, a voice per language; a `TextToSpeech`. `opener` replaces
    the WebSocket's connection and `transport` the HTTP transport (a test's fakes). Close it
    with `aclose()`."""

    name: str = "telnyx"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        languages: Mapping[LanguageTag, TtsVoice],
        timeout_s: float,
        trim_silence: bool = False,
        opener: Opener = open_socket,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = given_key(api_key, TelnyxSettings, VENDOR, instead=TTS_INSTEAD)
        self._languages: dict[str, TtsVoice] = dict(languages.items())
        self._timeout_s, self._trim = timeout_s, trim_silence
        self._open = opener
        self._http = http_client(timeout_s=timeout_s, transport=transport)

    @classmethod
    def from_settings(
        cls,
        settings: VoiceSettings,
        *,
        opener: Opener = open_socket,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> TelnyxTTS:
        """The adapter the settings describe: `telnyx`' key, `tts.languages`, `tts.timeout_s`
        and `tts.trim_silence`; a ConfigurationError naming `T2V_TELNYX__API_KEY` (under the
        settings' prefix) when no key is set."""
        key = provider_key(settings, settings.telnyx, VENDOR, instead=TTS_INSTEAD)
        tts = settings.tts
        return cls(
            api_key=key,
            languages=tts.languages,
            timeout_s=tts.timeout_s,
            trim_silence=tts.trim_silence,
            opener=opener,
            transport=transport,
        )

    def __repr__(self) -> str:
        voices = {tag: f"{v.model}.{v.voice}" for tag, v in self._languages.items()}
        return f"TelnyxTTS(languages={voices!r}, timeout_s={self._timeout_s!r})"

    def max_chars(self, language: str) -> int | None:
        """None: Telnyx states no limit for one take's text."""
        return None

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` spoken in `language`'s voice, chunk by chunk as Telnyx streams it (the port's
        `synthesize`; the module's docstring)."""
        voice = self._languages.get(language)
        if voice is None:
            raise no_voice()
        query = {"voice": f"{voice.model}.{voice.voice}", "audio_format": "linear16"}
        url = f"{STREAM_URL}?{urlencode({**query, 'sample_rate': RATE})}"
        take = PcmTake(rate=RATE, trim=self._trim)
        socket: Socket | None = None
        problem: ProviderError | None = None
        try:
            socket = await self._open(url, self._headers(), self._timeout_s)
            for message in ({"text": " "}, {"text": text}, {"text": ""}):
                await socket.send(json.dumps(message))
            while True:
                frame = await self._frame(socket)
                if frame is None or frame.isFinal:
                    break
                chunk = take.feed(frame.pcm())
                if chunk is not None:
                    yield chunk
        except _FrameError:
            details: dict[str, JsonValue] = {"provider": self.name, "error": "error_frame"}
            problem = ProviderError("server_error", True, details=details)
        except Exception as error:  # every failure, the socket's and the answer's; never a cancel
            problem = socket_failure(self.name, error)
        finally:
            await close_quietly(socket)
        if problem is not None:
            raise problem from None
        last = take.last(text, language)
        if last is not None:
            yield last

    async def _frame(self, socket: Socket) -> _Frame | None:
        """The next frame, within `timeout_s`; None once Telnyx has closed in order. An error
        frame raises `_FrameError`, one that is not Telnyx's `AnswerError`."""
        try:
            async with asyncio.timeout(self._timeout_s):
                raw = await socket.recv()
        except ConnectionClosedOK:
            return None
        frame = _Frame.read(raw)
        if frame.error is not None:
            raise _FrameError
        return frame

    async def check_language(self, language: str) -> datetime | None:
        """Return when `language` has a voice that Telnyx lists, with no synthesis (the port's
        `check_language`): one GET of the voices of its family's provider, which costs nothing;
        its time from the answer's `Date` header. ConfigurationError for a language with no
        voice; ProviderError (`rejected`) for a voice the list leaves out, and every failure."""
        voice = self._languages.get(language)
        if voice is None:
            setting = setting_name("tts", "languages")
            raise ConfigurationError(
                f"No text-to-speech model or voice is set for the language {language!r}. FIX: "
                f"give {setting} a model and a voice for it.",
                details={"setting": setting},
            )
        listed_as = LISTED_AS.get(voice.model, "telnyx")
        try:
            response = ok_status(
                await self._http.get(
                    VOICES_URL, params={"provider": listed_as}, headers=self._headers()
                )
            )
            ids = _Voices.model_validate_json(response.content).ids()
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            problem = http_failure(self.name, error)
        else:
            if f"{voice.model}.{voice.voice}" in ids:
                return server_time(response.headers)
            details: dict[str, JsonValue] = {"error": "voice_not_listed", "model": voice.model}
            problem = ProviderError("rejected", False, details=details)
        raise problem from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections; each take's socket is closed with its take."""
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}


class _FrameError(Exception):
    """Telnyx answered the take with an error frame (its text is never read)."""


class _Frame(BaseModel):
    """One frame of Telnyx's, as far as the adapter reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    audio: str | None = None
    isFinal: bool = False  # noqa: N815 - Telnyx's own name
    error: JsonValue = None

    @classmethod
    def read(cls, raw: Message) -> _Frame:
        try:
            return cls.model_validate_json(raw)
        except ValidationError:
            raise AnswerError("unreadable_frame") from None

    def pcm(self) -> bytes:
        """The frame's audio, decoded; none for a frame with no audio."""
        try:
            return base64.b64decode(self.audio or "", validate=True)
        except (binascii.Error, ValueError):
            raise AnswerError("unreadable_audio") from None


class _Voice(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    id: str


class _Voices(BaseModel):
    """Telnyx's voices list, as far as the adapter reads it: each voice's ID."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    voices: list[_Voice]

    def ids(self) -> set[str]:
        return {voice.id for voice in self.voices}
