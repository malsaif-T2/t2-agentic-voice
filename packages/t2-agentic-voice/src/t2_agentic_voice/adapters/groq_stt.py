"""Groq's Whisper behind the speech-to-text port (the design's 6.1; D-004).

`GroqSTT` sends one clip, wrapped as WAV, to Groq's transcription endpoint with the model
`stt.model` names, and returns its `Transcript`. It builds its client as every Groq adapter does
(`adapters/groq_client.py`: the key, base URL and timeout always passed, the SDK's retries off,
every request with the adapter's own headers, every failure a `ProviderError`, `groq` imported
with `GROQ_LOG` undone), and adds its own body's rule:

- The multipart boundary is the adapter's own, random and passed with each request: httpx would
  take a `GROQ_CUSTOM_HEADERS` `content-type` line's instead, so the request hook refuses a body
  that does not open with the adapter's, and such a line can only fail a request (a `rejected`
  ProviderError), never shape it, so audio that holds a known boundary cannot add a form field.
- Each answer's headroom, the requests and tokens Groq says the key has left, rides on its
  `Transcript`: the adapter asks for the SDK's raw response (`raw_response`), whose headers it
  reads (`headroom`) before it parses the answer as before.

The SDK's types stay inside this module; no public signature names one (the design's 5.3).
Public through the `groq` facade (D-021).
"""

from __future__ import annotations

import asyncio
import io
import secrets
import wave

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from t2_agentic_voice.adapters.groq_client import (
    DATA_FLOW,
    checked,
    failure,
    groq_client,
    headroom,
    no_key,
    omit,
    own_headers,
    raw_response,
)
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttModel, SttSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

# Groq bills every transcription request at least this long (its pricing, plan 002's
# registration, read 2026-11-01; the design's 10.4).
_MIN_BILLED_S = 10.0


class GroqSTT:
    """Speech-to-text with Groq's `whisper-large-v3` or `whisper-large-v3-turbo`; a
    `SpeechToText`. `transport` replaces the HTTP transport (a test's fake one); by default the
    adapter talks to `base_url` over its own connection pool. Close it with `aclose()`."""

    name: str = "groq"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: SttModel,
        base_url: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = checked(
            api_key, base_url, ("stt", lambda: SttSettings(model=model, timeout_s=timeout_s))
        )
        self._model: SttModel = model
        self._base_url = base_url
        self._timeout_s = timeout_s
        # The multipart boundary every request of this adapter carries (RFC 2046, 5.1.1).
        boundary = secrets.token_hex(16).encode("ascii")
        self._content_type = b"multipart/form-data; boundary=" + boundary
        hook = own_headers(
            self._api_key,
            accept=b"application/json",
            content_type=self._content_type,
            opens_with=b"--" + boundary + b"\r\n",
            refusal="foreign_boundary",
        )
        self._groq = groq_client(
            api_key=self._api_key,
            base_url=base_url,
            timeout_s=timeout_s,
            hook=hook,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> GroqSTT:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url`,
        `stt.model` and `stt.timeout_s`. ConfigurationError naming `T2V_GROQ__API_KEY` (under
        the settings' prefix) when no key is set, a blank one included, and saying so when
        `GROQ_API_KEY` is set instead: the library never reads it (the design's 7.3)."""
        key = settings.groq.resolved_api_key(settings.prefix)
        if key is None:
            raise no_key(
                settings.env_name("groq", "api_key"),
                settings.env_name("groq", "api_key_file"),
                settings.saw("GROQ_API_KEY"),
            )
        return cls(
            api_key=key,
            model=settings.stt.model,
            base_url=settings.groq.base_url,
            timeout_s=settings.stt.timeout_s,
            transport=transport,
        )

    def __repr__(self) -> str:
        return (
            f"GroqSTT(model={self._model!r}, base_url={self._base_url!r}, "
            f"timeout_s={self._timeout_s!r})"
        )

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`): Whisper's text with the space around
        it removed, the language named (else the one Groq reports), the confidence (Whisper's
        `avg_logprob`, a log-probability of 0 or below) and the no-speech estimate, each the
        mean over Whisper's segments weighted by their length, as the prototype weighted them,
        the billed seconds, never under Groq's minimum of 10 s, and the headroom Groq reported
        with the answer (each None when its header is absent or not a whole number). An empty
        `language` or `prompt` counts as none. The whole request, sent once, takes at most
        `timeout_s`. Raises ProviderError on every failure, an answer it cannot read included."""
        try:
            async with asyncio.timeout(self._timeout_s):
                with raw_response():
                    answer = await self._groq.audio.transcriptions.with_raw_response.create(
                        model=self._model,
                        file=("speech.wav", _wav(clip), "audio/wav"),
                        language=language or omit,
                        prompt=prompt or omit,
                        response_format="verbose_json",
                        temperature=0,
                        extra_headers={"Content-Type": self._content_type.decode("ascii")},
                    )
                result = await answer.parse()
            transcript = _Answer.model_validate(result.to_dict()).transcript(
                language or None,
                billed_seconds=max(_MIN_BILLED_S, clip.seconds),
                remaining=headroom(answer.headers),
            )
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            provider_error = failure(error)
        else:
            return transcript
        raise provider_error from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._groq.close()


class _Segment(BaseModel):
    """One of Whisper's segments, as far as the adapter reads it. A missing time counts as 0, as
    the prototype read it."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    start: float = 0.0
    end: float = 0.0
    avg_logprob: float | None = None
    no_speech_prob: float | None = Field(default=None, ge=0, le=1)

    @property
    def length(self) -> float:
        """The segment's weight: its length, at least 1 ms (the prototype's `_by_length`)."""
        return max(1e-3, self.end - self.start)


class _Answer(BaseModel):
    """Groq's `verbose_json` answer, as far as the adapter reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    text: str
    language: str | None = None
    segments: list[_Segment] = Field(default_factory=list)

    def transcript(
        self,
        language: str | None,
        *,
        billed_seconds: float,
        remaining: tuple[int | None, int | None],
    ) -> Transcript:
        confidence = [(s.length, s.avg_logprob) for s in self.segments if s.avg_logprob is not None]
        silence = [
            (s.length, s.no_speech_prob) for s in self.segments if s.no_speech_prob is not None
        ]
        return Transcript(
            text=self.text.strip(),
            language=language or self.language or None,
            confidence=_by_length(confidence),
            billed_seconds=billed_seconds,
            no_speech_prob=_by_length(silence),
            remaining_requests=remaining[0],
            remaining_tokens=remaining[1],
        )


def _by_length(parts: list[tuple[float, float]]) -> float | None:
    """The mean of a value per segment, (length, value), weighted by the segment's length; None
    with no segment (the prototype's `_by_length`)."""
    total = sum(length for length, _ in parts)
    return sum(length * value for length, value in parts) / total if parts else None


def _wav(clip: AudioClip) -> bytes:
    """`clip` as a WAV file: mono, 16-bit, at the clip's sample rate."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(clip.sample_rate)
        writer.writeframes(clip.pcm16)
    return buffer.getvalue()
