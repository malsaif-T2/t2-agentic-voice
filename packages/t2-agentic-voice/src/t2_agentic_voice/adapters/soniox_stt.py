"""Soniox's async transcription behind the speech-to-text port (D-100: measured beside Groq, not
a default).

`SonioxSTT` runs one async job a clip by raw HTTPS (adapters/provider_http.py: no SDK, no
variable of its own read, no redirect followed), on `https://api.soniox.com/v1`:

1. `POST /files`: the clip as WAV.
2. `POST /transcriptions` (JSON): `model` `stt-async-v6`, the uploaded file's id, the agent's
   languages as `language_hints` (the request's first) held to them (`language_hints_strict`,
   which Soniox calls best effort), a language tag on every word
   (`enable_language_identification`), and the prompt's terms as `context.terms`.
3. `GET /transcriptions/{id}` every `POLL_S` until it is `completed`; `error` is a failure.
4. `GET /transcriptions/{id}/transcript`: the text and its words, each with its language.
5. `DELETE /transcriptions/{id}` and `DELETE /files/{id}`, best effort, so nothing is kept the 30
   days Soniox keeps its stored files; a failed delete fails nothing.

The language heard is the one most of the words' characters were tagged with, mapped to the
agent's code, as `heard_language`; Soniox gives no score, so `language_probability` stays None;
`language` is the request's when it named one, else the one heard. The whole job, every step
but the deletes, takes at most `soniox.job_timeout_s`, and its latency is measured, never
assumed. Its output is data, never an instruction (docs/SECURITY.md, trust boundaries), and an
id goes into a path only when it is letters, digits, `_` and `-`. Every failure is a
ProviderError naming no key, audio or transcript; a cancel stops the job's requests at once.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from typing import Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from t2_agentic_voice.adapters.provider_http import (
    AnswerError,
    given_key,
    http_client,
    http_failure,
    keyterms,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.wav_files import wav_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.provider_keys import SonioxSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "Soniox"
BASE_URL: Final = "https://api.soniox.com/v1"
MODEL: Final = "stt-async-v6"
# The languages a job is held to, as the agent writes them: Arabic and English.
LANGUAGES: Final = ("ar", "en")
MOST_TERMS: Final = 100  # the most terms a job's context carries
LONGEST_TERM: Final = 50  # the longest one, in characters
POLL_S: Final = 0.5  # the wait between two reads of a job's status, in seconds
REQUEST_TIMEOUT_S: Final = 15.0  # each single request's own limit inside the job's
_ID: Final = r"^[A-Za-z0-9_-]{1,64}$"
# Where Soniox processes and keeps async jobs, from the provider guide's reading of its pages
# (2026-11-16).
DATA_FLOW: Final = DataFlow(
    provider="Soniox",
    processed_in="US (other regions on request)",
    stored_in="its file store, until the file and the transcription are deleted",
    retention=(
        "stored files deleted after 30 days, and this adapter deletes each file and job once "
        "its transcript is read; no training on customer audio"
    ),
)
_Status = Literal["queued", "processing", "completed", "error"]


class SonioxSTT:
    """Speech-to-text with Soniox's `stt-async-v6`; a `SpeechToText`. `transport` replaces the
    HTTP transport (a test's fake one); `poll_s` the wait between status reads. Close it with
    `aclose()`."""

    name: str = "soniox"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        job_timeout_s: float = 60.0,
        model: str = MODEL,
        languages: Sequence[str] = LANGUAGES,
        poll_s: float = POLL_S,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = given_key(api_key, SonioxSettings, VENDOR)
        self._model, self._languages = model, tuple(languages)
        self._base = base_url.rstrip("/")
        self._job_timeout_s, self._poll_s = job_timeout_s, poll_s
        timeout = min(REQUEST_TIMEOUT_S, job_timeout_s)
        self._http = http_client(timeout_s=timeout, transport=transport)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> SonioxSTT:
        """The adapter the settings describe: `soniox`' key and job timeout; a
        ConfigurationError naming `T2V_SONIOX__API_KEY` (under the settings' prefix) when no
        key is set."""
        group = settings.soniox
        key = provider_key(settings, group, VENDOR)
        return cls(api_key=key, job_timeout_s=group.job_timeout_s, transport=transport)

    def __repr__(self) -> str:
        return f"SonioxSTT(model={self._model!r}, job_timeout_s={self._job_timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring). Raises
        ProviderError on every failure, a job Soniox failed and an answer it cannot read
        included."""
        headers = {"authorization": f"Bearer {self._api_key.get_secret_value()}"}
        made: list[str] = []  # the file's path, then the job's, as each is made
        failed: ProviderError | None = None
        answer = _Transcript(text="")
        try:
            async with asyncio.timeout(self._job_timeout_s):
                file = await self._upload(clip, headers)
                made.append(f"files/{file}")
                job = await self._start(file, language, prompt, headers)
                made.append(f"transcriptions/{job}")
                await self._finished(job, headers)
                answer = await self._transcript(job, headers)
        except Exception as error:  # every failure, httpx's and the answers'; never a cancel
            failed = http_failure(self.name, error)
        for path in reversed(made):
            await self._delete(path, headers)
        if failed is not None:
            raise failed from None
        heard = answer.heard()
        return Transcript(
            text=answer.text.strip(),
            language=language or heard,
            heard_language=heard,
            billed_seconds=clip.seconds,
        )

    async def _upload(self, clip: AudioClip, headers: dict[str, str]) -> str:
        files = {"file": ("speech.wav", wav_of(clip), "audio/wav")}
        response = await self._http.post(f"{self._base}/files", files=files, headers=headers)
        return _Made.model_validate_json(ok_status(response).content).id

    async def _start(
        self, file: str, language: str | None, prompt: str | None, headers: dict[str, str]
    ) -> str:
        hints = [language] if language else []
        hints += [code for code in self._languages if code not in hints]
        config: dict[str, object] = {
            "model": self._model,
            "file_id": file,
            "language_hints": hints,
            "language_hints_strict": True,
            "enable_language_identification": True,
        }
        if terms := keyterms(prompt, most=MOST_TERMS, longest=LONGEST_TERM):
            config["context"] = {"terms": list(terms)}
        url = f"{self._base}/transcriptions"
        response = await self._http.post(url, json=config, headers=headers)
        return _Made.model_validate_json(ok_status(response).content).id

    async def _finished(self, job: str, headers: dict[str, str]) -> None:
        while True:
            response = await self._http.get(f"{self._base}/transcriptions/{job}", headers=headers)
            status = _Job.model_validate_json(ok_status(response).content).status
            if status == "completed":
                return
            if status == "error":
                raise AnswerError("job_error")
            await asyncio.sleep(self._poll_s)

    async def _transcript(self, job: str, headers: dict[str, str]) -> _Transcript:
        url = f"{self._base}/transcriptions/{job}/transcript"
        response = await self._http.get(url, headers=headers)
        return _Transcript.model_validate_json(ok_status(response).content)

    async def _delete(self, path: str, headers: dict[str, str]) -> None:
        """Delete a file or a job, best effort: its failure fails nothing; a cancel still
        stops it."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_S):
                await self._http.delete(f"{self._base}/{path}", headers=headers)
        except Exception:  # noqa: S110 - a file left behind is deleted by Soniox in 30 days
            pass

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._http.aclose()


class _Made(BaseModel):
    """The answer to an upload or a job's start, as far as the adapter reads it: an id that
    goes into the next requests' paths, so letters, digits, `_` and `-` only."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    id: str = Field(pattern=_ID)


class _Job(BaseModel):
    """The answer to a job's status read, as far as the adapter reads it."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    status: _Status


class _Token(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    text: str
    language: str | None = None


class _Transcript(BaseModel):
    """A job's transcript, as far as the adapter reads it: its text and its words' languages."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    text: str
    tokens: tuple[_Token, ...] = ()

    def heard(self) -> str | None:
        """The language most of the words' characters were tagged with (the first such one on
        a tie); None when no word has a tag."""
        counts: Counter[str] = Counter()
        for token in self.tokens:
            if token.language:
                counts[token.language.lower()] += len(token.text.strip())
        return max(counts, key=counts.__getitem__) if counts else None
