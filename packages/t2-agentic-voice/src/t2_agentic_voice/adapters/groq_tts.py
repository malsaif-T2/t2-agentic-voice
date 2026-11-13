"""Groq's Orpheus behind the text-to-speech port (the design's 6.1; D-004).

It speaks each language in the model and voice `tts.languages` gives it
(`canopylabs/orpheus-arabic-saudi` and `canopylabs/orpheus-v1-english`), one request per clause
with `response_format` "wav" passed explicitly, the request's fields as the baseline
records them (tests/t2_agentic_voice/fixtures/groq_tts_request.json). It builds its client as
every Groq adapter does (`adapters/groq_client.py`: the key, base URL and timeout always passed,
the SDK's retries off, every request with the adapter's own headers, a body that does not open
as its JSON does refused unsent, `groq` imported with `GROQ_LOG` undone). It refuses a text over
the model's `max_chars` (200 for both models), unsent; reads the sample rate from each WAV's
header, never assumes it (adapters/wav_stream.py); trims the silence before the speech only with
`tts.trim_silence` on; flags a take that came back cut short on its last chunk; puts each
response's `x-ratelimit-remaining-requests` and `x-ratelimit-remaining-tokens` on its first
chunk; and raises `ProviderError` for every failure, a model whose terms are not accepted
`rejected` with a FIX line that names the console's terms. Its `check_language` reads Groq's model
list raw, so it returns the time Groq sent it from its `Date` header, which `t2v doctor` measures
this machine's clock against. A cancel stops it within 50 ms, leaving no task or connection. No
public signature names a `groq` type (the design's 5.3). Public through the `groq` facade (D-021).

- **Streaming.** The answer is read as Groq streams it (the SDK's streamed response), each piece
  of audio a chunk as soon as it holds whole samples, so the first sound plays before the take
  has ended (the prototype's `stream`, its `voice/tts.py`, lines 191-221, read, never run).
  `tts.timeout_s` bounds each step of the request, the connection and each
  read of the answer, as the SDK's client applies it, not the whole take, which streams for as
  long as Groq takes to make it.
- **The last chunk.** A take's last chunk is known only once the stream has ended, so a take
  ends with one more chunk when it has audio still held, when it came back cut short (an empty
  chunk carrying `cut_short`), or when it gave no audio at all, so its headroom still reaches
  the call's usage.
- **Cut short** (the prototype's `cut_short`, its lines 24-36): a text of 30 characters or more
  whose speech, from its first sound to its end, runs faster than 24 characters a second in
  Arabic or 30 in English, or that has no speech at all. Flagged, never made again (plan 003's
  decision log).
- **Terms.** A model whose terms the key's organization has not accepted answers 400 with the
  code `model_terms_required` (quoted by a third party, github.com/langflow-ai/langflow/issues/
  11120, 2025-12-21; Groq's docs do not give it: UNVERIFIED). That refusal is `rejected`, its
  details naming the code and the model, with the FIX in its details' `fix` and as a note.
- **Failures** go through `groq_client.failure`; a read of the streamed answer that times out
  or loses its connection, which the SDK does not wrap, is `timeout` or `connection_lost`
  (`groq_client.stream_failure`), and an answer that is not a mono 16-bit WAV is a
  `server_error`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, ValidationError

from t2_agentic_voice.adapters.groq_client import (
    DATA_FLOW,
    APIStatusError,
    checked,
    failure,
    groq_client,
    headroom,
    own_headers,
    raw_response,
    server_time,
    settings_key,
    stream_failure,
)
from t2_agentic_voice.adapters.wav_stream import WavStream
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsModel, TtsSettings, TtsVoice
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

# The longest text one request of each model takes, in characters (Groq's Orpheus page,
# console.groq.com/docs/text-to-speech/orpheus, read 2026-11-02 by plan 003's research step).
MAX_CHARS: Mapping[TtsModel, int] = {
    "canopylabs/orpheus-arabic-saudi": 200,
    "canopylabs/orpheus-v1-english": 200,
}
# The cut-short check (the prototype's tts.py, lines 24-36): faster than this many characters a
# second of speech, a take lost words; a text under SHORT_TEXT characters says too little to tell.
CHARS_PER_SECOND_MAX: Mapping[str, float] = {"ar": 24.0, "en": 30.0}
SHORT_TEXT = 30
# The code Groq answers a model whose terms are not accepted with (UNVERIFIED, above).
TERMS_CODE = "model_terms_required"
# The SDK's speech body opens with its first field, the text (groq/resources/audio/speech.py).
_OPENS_WITH = b'{"input":'


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
        self._api_key = checked(
            api_key,
            base_url,
            (
                "tts",
                lambda: TtsSettings(
                    languages=languages, timeout_s=timeout_s, trim_silence=trim_silence
                ),
            ),
        )
        self._languages: dict[str, TtsVoice] = dict(languages.items())
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._trim_silence = trim_silence
        hook = own_headers(
            self._api_key,
            accept=b"audio/wav",
            content_type=b"application/json",
            opens_with=_OPENS_WITH,
            refusal="foreign_body",
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
    ) -> GroqTTS:
        """The adapter the settings describe: `groq.resolved_api_key()`, `groq.base_url`,
        `tts.languages`, `tts.timeout_s` and `tts.trim_silence`. ConfigurationError naming
        `T2V_GROQ__API_KEY` (under the settings' prefix) when no key is set, as `GroqSTT`'s."""
        key = settings_key(settings)
        return cls(
            api_key=key,
            languages=settings.tts.languages,
            base_url=settings.groq.base_url,
            timeout_s=settings.tts.timeout_s,
            trim_silence=settings.tts.trim_silence,
            transport=transport,
        )

    def __repr__(self) -> str:
        voices = {tag: f"{v.model}:{v.voice}" for tag, v in self._languages.items()}
        return (
            f"GroqTTS(languages={voices!r}, base_url={self._base_url!r}, "
            f"timeout_s={self._timeout_s!r}, trim_silence={self._trim_silence!r})"
        )

    def max_chars(self, language: str) -> int | None:
        """The longest text one request of `language` takes (the port's `max_chars`): its
        model's, 200 for both; for a language with no model, the least of them, since no text
        of it can be spoken."""
        voice = self._languages.get(language)
        return MAX_CHARS[voice.model] if voice else min(MAX_CHARS.values())

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        """`text` spoken in `language`'s model and voice, chunk by chunk as Groq streams it (the
        port's `synthesize`). A language with no model and a text over `max_chars` are
        `rejected` ProviderErrors, unsent."""
        voice = self._languages.get(language)
        if voice is None:
            raise ProviderError("rejected", False, details={"error": "no_voice"})
        limit = MAX_CHARS[voice.model]
        if len(text) > limit:
            raise ProviderError(
                "rejected", False, details={"error": "too_long", "max_chars": limit}
            )
        wav = WavStream(trim=self._trim_silence)
        remaining: tuple[int | None, int | None] = (None, None)
        sent, tail = 0, b""
        problem: ProviderError | None = None
        try:
            async with self._groq.audio.speech.with_streaming_response.create(
                model=voice.model, voice=voice.voice, input=text, response_format="wav"
            ) as response:
                remaining = headroom(response.headers)
                async for data in response.iter_bytes():
                    pcm = wav.feed(data)
                    if pcm:
                        yield _chunk(pcm, wav.sample_rate, remaining if not sent else None)
                        sent += 1
            tail = wav.finish()
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            problem = _failure(error, voice.model)
        if problem is not None:
            raise problem from None
        short = cut_short(text, language, wav.speech_s)
        if tail or short or not sent:
            yield _chunk(tail, wav.sample_rate, remaining if not sent else None, cut=short)

    async def check_language(self, language: str) -> datetime | None:
        """Return when `language` has a model and a voice and Groq lists the model, with no
        synthesis (the port's `check_language`): one GET of Groq's model list, asked for raw so
        its headers are read. It returns when Groq sent the list, from its `Date` header
        (`groq_client.server_time`), None when the answer has none it can read.
        ConfigurationError for a language with no model or voice; ProviderError (`rejected`)
        for a model the list leaves out, and for every failure of the request."""
        voice = self._languages.get(language)
        if voice is None:
            setting = setting_name("tts", "languages")
            raise ConfigurationError(
                f"No text-to-speech model or voice is set for the language {language!r}. FIX: "
                f"give {setting} a model and a voice for it.",
                details={"setting": setting},
            )
        problem: ProviderError | None = None
        try:
            with raw_response():
                answer = await self._groq.models.with_raw_response.list()
            models = _Listing.model_validate((await answer.parse()).to_dict()).ids()
            sent_at = server_time(answer.headers)
        except Exception as error:  # every failure, the SDK's and the answer's; never a cancel
            problem = failure(error)
        if problem is not None:
            raise problem from None
        if voice.model not in models:
            fix = (
                f"FIX: give {setting_name('tts', 'languages')} a model Groq lists for this key, "
                "or open the model to the key's organization in Groq's console."
            )
            details: dict[str, JsonValue] = {"error": "model_not_listed", "model": voice.model}
            raise _with_fix(ProviderError("rejected", False, details=details), fix)
        return sent_at

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._groq.close()


def cut_short(text: str, language: str, speech_s: float) -> bool:
    """Whether a take of `text` in `language` that holds `speech_s` seconds of speech, from its
    first sound to its end, came back shorter than its text needs (above)."""
    if len(text) < SHORT_TEXT:
        return False
    ceiling = CHARS_PER_SECOND_MAX[primary_code(language)]
    return speech_s <= 0 or len(text) / speech_s > ceiling


def _chunk(
    pcm: bytes,
    rate: int,
    remaining: tuple[int | None, int | None] | None,
    *,
    cut: bool = False,
) -> AudioChunk:
    """One chunk of a take, with the response's headroom when it is the take's first, and
    `cut` when it is the last of a take cut short."""
    requests, tokens = remaining or (None, None)
    return AudioChunk(
        pcm16=pcm,
        sample_rate=rate,
        remaining_requests=requests,
        remaining_tokens=tokens,
        cut_short=cut,
    )


def _failure(error: Exception, model: str) -> ProviderError:
    """The ProviderError for a failure of a speech request on `model` (above)."""
    mapped = stream_failure(error)
    if not (isinstance(error, APIStatusError) and _Refusal.code_of(error.body) == TERMS_CODE):
        return mapped
    mapped.details |= {"error": TERMS_CODE, "model": model}
    return _with_fix(
        mapped,
        f"FIX: accept the terms of {model} in Groq's console (console.groq.com/playground, with "
        "the model chosen), signed in as the key's organization's admin, then try again.",
    )


def _with_fix(error: ProviderError, fix: str) -> ProviderError:
    """`error` with its FIX line in its details' `fix` and as a note, which a traceback shows."""
    error.details["fix"] = fix
    error.add_note(fix)
    return error


class _Code(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    code: str | None = None


class _Refusal(BaseModel):
    """The body of a refusal, as far as the adapter reads it: OpenAI's error shape, which Groq
    answers with, `{"error": {"message": ..., "type": ..., "code": ...}}`."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    error: _Code

    @classmethod
    def code_of(cls, body: object) -> str | None:
        """The refusal's code, or None for a body of another shape."""
        try:
            return cls.model_validate(body).error.code
        except ValidationError:
            return None


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    id: str


class _Listing(BaseModel):
    """Groq's model list, as far as the adapter reads it: each model's ID."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    data: list[_Model]

    def ids(self) -> set[str]:
        return {model.id for model in self.data}
