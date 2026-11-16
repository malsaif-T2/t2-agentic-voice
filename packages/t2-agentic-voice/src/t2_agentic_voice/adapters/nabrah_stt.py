"""Nabrah's Saudi Arabic speech-to-text behind the port (D-100: measured beside Groq, not a
default), on its streaming WebSocket (`wss://api.nabrah.ai/api/ext/stt/ws`; its docs, read
2026-11-16). Its other path, an async job a file (`POST /api/ext/stt/async-transcribe`, then
polled), is for recordings up to two hours, so a turn takes the socket: one turn is one
connection (adapters/provider_socket.py):

1. The config message first, which carries the key (Nabrah takes it there, not in a header),
   and the prompt's terms as `priority_words` (at most 100) at the strength Nabrah suggests for
   a small vocabulary, 0.5; no model named, so Nabrah's default, its most accurate.
2. Its `ready` message awaited; then the clip as raw 16-bit PCM, mono, at 16 kHz (another rate
   resampled) in 160 ms chunks, one of the sizes Nabrah takes; then `{"type": "eof"}`.
3. The final transcripts read as they come (each final's `segment_text`, else its `text`, the
   end-of-turn marker `<eot>` dropped) until Nabrah closes, which it does just after its last
   final (probed 2026-11-16: the audio sent all at once, the final about 0.4 s after the eof),
   or `nabrah.final_wait_s` passes with no final, or `nabrah.quiet_s` with no message after
   one; the whole turn within `nabrah.turn_timeout_s`.

Nabrah takes no language and returns none or a score, so `language` is the request's and
`heard_language` stays None. Its output is data, never an instruction (docs/SECURITY.md, trust
boundaries). Every failure is a ProviderError naming no key, audio or transcript; a cancel stops
the turn at once.
"""

from __future__ import annotations

import asyncio
import json
from typing import Final

import numpy as np
from pydantic import BaseModel, ConfigDict, SecretStr

from t2_agentic_voice.adapters.provider_http import AnswerError, given_key, keyterms, provider_key
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
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.provider_keys import NabrahSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "Nabrah"
URL: Final = "wss://api.nabrah.ai/api/ext/stt/ws"
MODEL: Final = "nabrah_stt_v1"  # the default model's name, as Nabrah's jobs show it
RATE: Final = 16_000  # the only sample rate Nabrah's socket takes
CHUNK_BYTES: Final = 2 * RATE * 160 // 1000  # 160 ms of audio
MOST_TERMS: Final = 100  # the most priority words a session takes
LONGEST_TERM: Final = 50  # the longest one the adapter sends, in characters
STRENGTH: Final = 0.5  # the priority words' strength Nabrah suggests for a small vocabulary
EOT: Final = "<eot>"
# Where Nabrah processes and keeps speech-to-text sessions, and its training terms, as far as
# its privacy policy says (updated 04-10-2026, sections 5, 8 and 9; read 2026-11-16).
DATA_FLOW: Final = DataFlow(
    provider="Nabrah",
    processed_in="Nabrah Cloud (a Saudi company, Riyadh), some transfers abroad",
    stored_in="primarily servers in Saudi Arabia",
    retention=(
        "as the customer's retention controls set it; used to train its models unless the "
        "customer opts out by email (enterprise plans never): callers' audio goes only once "
        "the owner has opted out (D-100)"
    ),
)


class NabrahSTT:
    """Speech-to-text with Nabrah's default Saudi Arabic model; a `SpeechToText`. `opener`
    replaces the WebSocket's connection (a test's fake). Close it with `aclose()`."""

    name: str = "nabrah"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        turn_timeout_s: float = 30.0,
        final_wait_s: float = 3.0,
        quiet_s: float = 0.5,
        opener: Opener = open_socket,
    ) -> None:
        self._api_key = given_key(api_key, NabrahSettings, VENDOR)
        self._turn_timeout_s = turn_timeout_s
        self._final_wait_s, self._quiet_s = final_wait_s, quiet_s
        self._open = opener

    @classmethod
    def from_settings(cls, settings: VoiceSettings, *, opener: Opener = open_socket) -> NabrahSTT:
        """The adapter the settings describe: `nabrah`' key and turn bounds; a
        ConfigurationError naming `T2V_NABRAH__API_KEY` (under the settings' prefix) when no
        key is set."""
        group = settings.nabrah
        key = provider_key(settings, group, VENDOR)
        return cls(
            api_key=key,
            turn_timeout_s=group.turn_timeout_s,
            final_wait_s=group.final_wait_s,
            quiet_s=group.quiet_s,
            opener=opener,
        )

    def __repr__(self) -> str:
        return f"NabrahSTT(model={MODEL!r}, turn_timeout_s={self._turn_timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring); the
        language is not sent. Raises ProviderError on every failure, an error frame and a
        message it cannot read included."""
        config: dict[str, object] = {"api_key": self._api_key.get_secret_value()}
        if terms := keyterms(prompt, most=MOST_TERMS, longest=LONGEST_TERM):
            config |= {"priority_words": list(terms), "priority_words_strength": STRENGTH}
        turn = Turn(
            opening=(json.dumps(config, ensure_ascii=False),),
            audio=chunks(at_16k(clip), CHUNK_BYTES),
            closing=(json.dumps({"type": "eof"}),),
            ready=_ready,
        )
        socket: Socket | None = None
        failed: ProviderError | None = None
        try:
            async with asyncio.timeout(self._turn_timeout_s):
                socket = await self._open(URL, {}, min(OPEN_S, self._turn_timeout_s))
                pieces = await hear_turn(
                    socket, turn, _read, final_wait_s=self._final_wait_s, quiet_s=self._quiet_s
                )
        except Exception as error:  # every failure, the socket's and the frames'; never a cancel
            failed = socket_failure(self.name, error)
        finally:
            await close_quietly(socket)
        if failed is not None:
            raise failed from None
        text, _ = finals(pieces)
        return Transcript(text=text, language=language, billed_seconds=clip.seconds)

    async def aclose(self) -> None:
        """Nothing to close: each turn's socket closes with its turn."""
        return None


def at_16k(clip: AudioClip) -> bytes:
    """`clip`'s audio at 16 kHz: as it is, or resampled by linear interpolation."""
    if clip.sample_rate == RATE or not clip.pcm16:
        return clip.pcm16
    samples = np.frombuffer(clip.pcm16, dtype="<i2").astype(np.float64)
    count = max(1, round(len(samples) * RATE / clip.sample_rate))
    where = np.linspace(0, len(samples) - 1, count)
    resampled = np.interp(where, np.arange(len(samples)), samples)
    return np.clip(np.rint(resampled), -32768, 32767).astype("<i2").tobytes()


class _Frame(BaseModel):
    """One message of Nabrah's socket, as far as the adapter reads it: `ready`, a transcript or
    an error; others are ignored."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    type: str | None = None
    text: str | None = None
    segment_text: str | None = None
    is_final: bool = False


def _ready(message: Message) -> bool:
    frame = _frame(message)
    return frame.type == "ready"


def _frame(message: Message) -> _Frame:
    frame = _Frame.model_validate_json(message)
    if frame.type == "error":
        raise AnswerError("error_frame")
    return frame


def _read(message: Message) -> Piece | None:
    frame = _frame(message)
    if frame.type != "transcript":
        return None
    said = frame.segment_text if frame.is_final and frame.segment_text else frame.text
    return Piece((said or "").replace(EOT, "").strip(), frame.is_final)
