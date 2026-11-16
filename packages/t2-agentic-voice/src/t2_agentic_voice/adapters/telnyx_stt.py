"""Telnyx's speech-to-text behind the port (D-100: measured beside Groq, not a default), with
the model `telnyx.stt_model` names:

- `humain/realtime` (the default): HUMAIN's Arabic engine, with Arabic-English code-switching,
  which Telnyx runs only on its streaming WebSocket (`wss://api.telnyx.com/v2/speech-to-text/
  transcription`, engine `Humain`; its batch endpoint lists no such model, its docs read
  2026-11-16). One turn is one connection (adapters/provider_socket.py): the clip as raw 16-bit
  PCM at its own rate in 100 ms chunks, then `TAIL_S` of silence so the engine ends the
  utterance, then `CloseStream` (which an engine that has none ignores); the final transcripts
  read until Telnyx closes, or `telnyx.quiet_s` passes with no message, the whole turn within
  `telnyx.turn_timeout_s`. The language is the request's (`ar` or `en`), or `codeswitch` when it
  names none. Each final's `confidence` is averaged into the transcript's `confidence`, from 0
  to 1; Telnyx returns no language, so `heard_language` stays None.
- `deepgram/nova-3` or `openai/whisper-large-v3-turbo`: Telnyx's OpenAI-style batch endpoint
  (`POST /v2/ai/audio/transcriptions`, multipart), by raw HTTPS (adapters/provider_http.py), the
  clip as WAV, the language named when the request names one, `stt.timeout_s` for the request.

The key goes as a bearer token in the request's or the handshake's header. No prompt: neither
path takes one for these models. Its output is data, never an instruction (docs/SECURITY.md,
trust boundaries). Every failure is a ProviderError naming no key, audio or transcript; a cancel
stops the turn at once.
"""

from __future__ import annotations

import asyncio
import json
from typing import Final
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr

from t2_agentic_voice.adapters.provider_http import (
    AnswerError,
    given_key,
    http_client,
    http_failure,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.provider_socket import (
    OPEN_S,
    Message,
    Opener,
    Piece,
    Socket,
    Turn,
    chunks,
    close_quietly,
    finals,
    hear_turn,
    open_socket,
    socket_failure,
)
from t2_agentic_voice.adapters.wav_files import wav_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.provider_keys import TelnyxSettings, TelnyxSttModel
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "Telnyx"
BATCH_URL: Final = "https://api.telnyx.com/v2/ai/audio/transcriptions"
STREAM_URL: Final = "wss://api.telnyx.com/v2/speech-to-text/transcription"
MODEL: Final[TelnyxSttModel] = "humain/realtime"
# The engine each model Telnyx runs only on its WebSocket is named by there.
STREAMED: Final[dict[str, str]] = {"humain/realtime": "Humain"}
CODESWITCH: Final = "codeswitch"  # HUMAIN's language for Arabic and English in one turn
TAIL_S: Final = 1.0  # the silence after a turn's audio, in seconds, so the engine ends it
CHUNK_S: Final = 0.1  # each audio message's length, in seconds
# Where Telnyx processes and keeps speech-to-text requests, as far as its pages say (read
# 2026-11-16); its data terms are to be read before callers' audio goes (docs/SECURITY.md).
DATA_FLOW: Final = DataFlow(
    provider="Telnyx",
    processed_in=(
        "Telnyx's network (US-based); the humain/realtime engine is HUMAIN's, run through "
        "Telnyx, where it runs not stated"
    ),
    stored_in="not stated by Telnyx for speech-to-text requests",
    retention="not stated on its speech-to-text pages",
)


class TelnyxSTT:
    """Speech-to-text through Telnyx (`model`, `humain/realtime` by default); a
    `SpeechToText`. `transport` replaces the batch path's HTTP transport, `opener` the
    WebSocket's connection (a test's fakes). Close it with `aclose()`."""

    name: str = "telnyx"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        timeout_s: float,
        model: TelnyxSttModel = MODEL,
        turn_timeout_s: float = 20.0,
        quiet_s: float = 1.5,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: Opener = open_socket,
    ) -> None:
        self._api_key = given_key(api_key, TelnyxSettings, VENDOR)
        self._model = model
        self._timeout_s, self._turn_timeout_s, self._quiet_s = timeout_s, turn_timeout_s, quiet_s
        self._http = http_client(timeout_s=timeout_s, transport=transport)
        self._open = opener

    @classmethod
    def from_settings(
        cls,
        settings: VoiceSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: Opener = open_socket,
    ) -> TelnyxSTT:
        """The adapter the settings describe: `telnyx`' key, model and turn bounds, and
        `stt.timeout_s`; a ConfigurationError naming `T2V_TELNYX__API_KEY` (under the settings'
        prefix) when no key is set."""
        group = settings.telnyx
        return cls(
            api_key=provider_key(settings, group, VENDOR),
            timeout_s=settings.stt.timeout_s,
            model=group.stt_model,
            turn_timeout_s=group.turn_timeout_s,
            quiet_s=group.quiet_s,
            transport=transport,
            opener=opener,
        )

    def __repr__(self) -> str:
        return f"TelnyxSTT(model={self._model!r}, timeout_s={self._timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring); `prompt`
        is not sent. Raises ProviderError on every failure, an error frame and an answer it
        cannot read included."""
        if self._model in STREAMED:
            return await self._streamed(clip, language)
        return await self._batch(clip, language)

    async def _batch(self, clip: AudioClip, language: str | None) -> Transcript:
        fields = {"model": self._model, "response_format": "json"}
        if language:
            fields["language"] = language
        headers = {"authorization": f"Bearer {self._api_key.get_secret_value()}"}
        files = {"file": ("speech.wav", wav_of(clip), "audio/wav")}
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._http.post(
                    BATCH_URL, data=fields, files=files, headers=headers
                )
            text = _Batch.model_validate_json(ok_status(response).content).text
        except Exception as error:  # every failure, httpx's and the answer's; never a cancel
            failed = http_failure(self.name, error)
        else:
            return Transcript(text=text.strip(), language=language, billed_seconds=clip.seconds)
        raise failed from None

    async def _streamed(self, clip: AudioClip, language: str | None) -> Transcript:
        query = {
            "transcription_engine": STREAMED[self._model],
            "model": self._model,
            "input_format": "linear16",
            "sample_rate": clip.sample_rate,
            "language": language or CODESWITCH,
        }
        url = f"{STREAM_URL}?{urlencode(query)}"
        headers = {"authorization": f"Bearer {self._api_key.get_secret_value()}"}
        tail = bytes(2 * round(clip.sample_rate * TAIL_S))
        size = 2 * round(clip.sample_rate * CHUNK_S)
        turn = Turn(
            opening=(),
            audio=chunks(clip.pcm16 + tail, size),
            closing=(json.dumps({"type": "CloseStream"}),),
        )
        socket: Socket | None = None
        failed: ProviderError | None = None
        try:
            async with asyncio.timeout(self._turn_timeout_s):
                socket = await self._open(url, headers, min(OPEN_S, self._turn_timeout_s))
                pieces = await hear_turn(socket, turn, _read, quiet_s=self._quiet_s)
        except Exception as error:  # every failure, the socket's and the frames'; never a cancel
            failed = socket_failure(self.name, error)
        finally:
            await close_quietly(socket)
        if failed is not None:
            raise failed from None
        text, confidence = finals(pieces)
        billed = clip.seconds + TAIL_S
        return Transcript(
            text=text, language=language, confidence=confidence, billed_seconds=billed
        )

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections (each turn's socket closes with its turn)."""
        await self._http.aclose()


class _Batch(BaseModel):
    """The batch endpoint's answer, as far as the adapter reads it."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    text: str


class _Frame(BaseModel):
    """One message of Telnyx's WebSocket, as far as the adapter reads it: a transcript, or an
    error (`errors`, or `type` "error"); others are ignored."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    type: str | None = None
    transcript: str | None = None
    is_final: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    errors: JsonValue = None


def _read(message: Message) -> Piece | None:
    frame = _Frame.model_validate_json(message)
    if frame.errors is not None or frame.type == "error":
        raise AnswerError("error_frame")
    if frame.transcript is None:
        return None
    return Piece(frame.transcript, frame.is_final, frame.confidence)
