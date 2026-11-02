"""Groq's Whisper behind the speech-to-text port (the design's 6.1; D-004).

`GroqSTT` sends one clip, wrapped as WAV, to Groq's transcription endpoint with the model
`stt.model` names, and returns its `Transcript`. How it keeps to the design's 7.3 ("Other names
are never read") and keeps the key out of everything but the request, as plan 002's decision log
reads groq 1.7.0 (tests/t2_agentic_voice/test_read_versions.py fails on another version):

- The key, `groq.base_url` and the timeout are always passed to the SDK, so it never falls back
  to `GROQ_API_KEY` or `GROQ_BASE_URL`. Its own retries are off: the caller asks again, and
  counts every attempt.
- The SDK reads `GROQ_CUSTOM_HEADERS` whatever is passed, and its lines sit over the
  `Authorization` header the SDK builds from the key. So the HTTP client the adapter gives it
  has a request hook that replaces every header with the adapter's own: a fixed list, each with
  a value the adapter sets, `Authorization` the settings' key. No line of that variable, in any
  case, adds a header, sends another key or a second one, or changes a header's value. The
  multipart boundary is the adapter's own, random and passed with each request: httpx would take
  a `content-type` line's instead, so the hook refuses a body that does not open with the
  adapter's, and such a line can only fail a request (a `rejected` ProviderError), never shape
  it, so audio that holds a known boundary cannot add a form field.
- Every exception the SDK raises becomes a `ProviderError`, raised after the handler and from
  None, so no exception chain leads to the SDK's error, which holds the request and its
  headers. A cancel is never caught: the request ends at once and its connection is closed.
- `GROQ_LOG`, which `groq` reads when it is imported, is undone: `groq` is imported inside
  `core.logging.logging_unchanged`, which removes the root handler the SDK adds and puts the
  `groq` and `httpx` loggers' levels back (only `core` may import `logging`, ARCH-OWNER). An app
  that imports `groq` before the library keeps the variable's effect (TD-003).

The SDK's types stay inside this module; no public signature names one (the design's 5.3).
Public through the `groq` facade (D-021).
"""

from __future__ import annotations

import asyncio
import io
import math
import secrets
import wave

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, ValidationError

from t2_agentic_voice.core.config import (
    KEY_FILE_SETTING,
    KEY_SETTING,
    GroqSettings,
    Settings,
    SttModel,
    SttSettings,
    setting_name,
)
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.logging import logging_unchanged
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

with logging_unchanged("groq", "httpx"):  # groq reads GROQ_LOG on import (TD-003)
    from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq, omit
    from groq import __version__ as groq_version

# Groq bills every transcription request at least this long (its pricing, plan 002's
# registration, read 2026-11-01; the design's 10.4).
_MIN_BILLED_S = 10.0
# The prototype's connection pool (its `groqhttp.py`, read 2026-11-01): a connection is kept open
# five minutes, since httpx's 5 s left every utterance paying a new TLS handshake.
_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=300.0)
# What the SDK sends as its own user agent (`AsyncGroq/Python <version>`).
_USER_AGENT = f"AsyncGroq/Python {groq_version}".encode("ascii")
# Groq's "Your Data" page, as the design's 6.1 gives it.
_DATA_FLOW = DataFlow(
    provider="Groq",
    processed_in="not stated by the provider",
    stored_in="US (Google Cloud buckets), for data Groq retains",
    retention=(
        "none by default for inference; reliability and abuse logs up to 30 days unless Zero "
        "Data Retention is on or log storage is opted out"
    ),
)


class GroqSTT:
    """Speech-to-text with Groq's `whisper-large-v3` or `whisper-large-v3-turbo`; a
    `SpeechToText`. `transport` replaces the HTTP transport (a test's fake one); by default the
    adapter talks to `base_url` over its own connection pool. Close it with `aclose()`."""

    name: str = "groq"
    data_flow: DataFlow = _DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: SttModel,
        base_url: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = _checked(api_key, model, base_url, timeout_s)
        key = self._api_key.get_secret_value()
        self._model: SttModel = model
        self._base_url = base_url
        self._timeout_s = timeout_s
        # The multipart boundary every request of this adapter carries (RFC 2046, 5.1.1).
        self._boundary = secrets.token_hex(16).encode("ascii")
        http = httpx.AsyncClient(
            transport=transport,
            limits=_LIMITS,
            timeout=timeout_s,
            follow_redirects=False,  # a redirect would carry the key to another host
            event_hooks={"request": [self._own_headers]},
        )
        self._groq = AsyncGroq(
            api_key=key,
            base_url=base_url,
            timeout=timeout_s,
            max_retries=0,
            default_headers={"Authorization": f"Bearer {key}"},
            http_client=http,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> GroqSTT:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url`,
        `stt.model` and `stt.timeout_s`. ConfigurationError naming `T2V_GROQ__API_KEY` when no
        key is set, a blank one included; `GROQ_API_KEY` is never read (the design's 7.3)."""
        key = settings.groq.resolved_api_key()
        if key is None:
            raise _no_key()
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
        and the billed seconds, never under Groq's minimum of 10 s. An empty
        `language` or `prompt` counts as none. The whole request, sent once, takes at most
        `timeout_s`. Raises ProviderError on every failure, an answer it cannot read included."""
        try:
            async with asyncio.timeout(self._timeout_s):
                result = await self._groq.audio.transcriptions.create(
                    model=self._model,
                    file=("speech.wav", _wav(clip), "audio/wav"),
                    language=language or omit,
                    prompt=prompt or omit,
                    response_format="verbose_json",
                    temperature=0,
                    extra_headers={"Content-Type": self._content_type().decode("ascii")},
                )
            transcript = _Answer.model_validate(result.to_dict()).transcript(
                language or None, billed_seconds=max(_MIN_BILLED_S, clip.seconds)
            )
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            failure = _failure(error)
        else:
            return transcript
        raise failure from None

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._groq.close()

    def _content_type(self) -> bytes:
        return b"multipart/form-data; boundary=" + self._boundary

    async def _own_headers(self, request: httpx.Request) -> None:
        """The request hook: every request carries these eight headers and no other, each with
        the adapter's value, in whatever case the SDK or `GROQ_CUSTOM_HEADERS` named them. A body
        that does not open with the adapter's boundary line (`--<boundary>`, RFC 2046) was cut by
        another boundary, a `content-type` line's, and is never sent; the length is the body's."""
        body = await request.aread()
        if not body.startswith(b"--" + self._boundary + b"\r\n"):
            raise _ForeignBoundaryError
        key = self._api_key.get_secret_value().encode("ascii")
        request.headers = httpx.Headers(
            {
                b"Host": request.url.netloc,
                b"Accept": b"application/json",
                b"Accept-Encoding": b"gzip, deflate",
                b"Connection": b"keep-alive",
                b"User-Agent": _USER_AGENT,
                b"Content-Type": self._content_type(),
                b"Content-Length": str(len(body)).encode("ascii"),
                b"Authorization": b"Bearer " + key,
            }
        )


class _ForeignBoundaryError(Exception):
    """A body cut by a boundary other than the adapter's. It holds no value: the SDK logs it at
    DEBUG, with its traceback, as it wraps it in an APIConnectionError."""


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

    def transcript(self, language: str | None, *, billed_seconds: float) -> Transcript:
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


def _failure(error: Exception) -> ProviderError:
    """The ProviderError for one failure. Its details hold the failure's class name and the HTTP
    status, if any: never the SDK's message or body, which may echo the request. A status is
    retryable where the SDK's own retry rule would ask again (408, 409, 429 and 5xx); an answer
    that cannot be read, or any other failure, is a server error not worth asking again for; a
    body the hook refused, never sent, is rejected."""
    details: dict[str, JsonValue] = {"error": type(error).__name__}
    if isinstance(error, APIConnectionError) and isinstance(error.__cause__, _ForeignBoundaryError):
        details["error"] = "foreign_boundary"  # never sent: asking again fails the same way
        return ProviderError("rejected", False, details=details)
    if isinstance(error, APITimeoutError | TimeoutError):
        return ProviderError("timeout", True, details=details)
    if isinstance(error, APIConnectionError):
        return ProviderError("connection_lost", True, details=details)
    if not isinstance(error, APIStatusError):
        return ProviderError("server_error", False, details=details)
    status = error.status_code
    details["status"] = status
    if status == 429:
        delay = _retry_after(error.response.headers.get("retry-after"))
        return ProviderError("rate_limited", True, delay, details=details)
    if status == 408:
        return ProviderError("timeout", True, details=details)
    if status == 409 or status >= 500:
        return ProviderError("server_error", True, details=details)
    return ProviderError("rejected", False, details=details)


def _retry_after(value: str | None) -> float | None:
    """The delay a `retry-after` header asks for, in seconds; None unless it is a finite number of
    seconds, 0 or more (an HTTP date is not read)."""
    try:
        seconds = float(value or "")
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _no_key() -> ConfigurationError:
    return ConfigurationError(
        f"No Groq API key is set. FIX: set {KEY_SETTING}, or {KEY_FILE_SETTING} to a file "
        "that holds the key.",
        details={"setting": KEY_SETTING},
    )


def _checked(api_key: SecretStr, model: SttModel, base_url: str, timeout_s: float) -> SecretStr:
    """The key, as `GroqSettings.resolved_api_key` gives it, once the settings' own models take
    every value: for a team that builds the adapter in code, the constructor refuses what the
    settings refuse as they load, by the same rules (GP-20). Each error names the setting and
    never the value; it is raised outside the handler, so no exception chain leads to it."""
    checks = (
        ("groq", lambda: GroqSettings(api_key=api_key, base_url=base_url)),
        ("stt", lambda: SttSettings(model=model, timeout_s=timeout_s)),
    )
    for group, check in checks:
        try:
            check()
        except ValidationError as error:
            problem = error.errors(include_input=False, include_url=False)[0]
        else:
            continue
        setting = setting_name(group, *problem["loc"])
        raise ConfigurationError(
            f"The Groq adapter refuses its {setting} ({problem['msg']}). FIX: give it a value "
            "the settings take.",
            details={"setting": setting},
        )
    key = GroqSettings(api_key=api_key).resolved_api_key()
    if key is None:
        raise _no_key()
    return key
