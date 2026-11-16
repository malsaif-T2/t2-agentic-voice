"""Speechmatics' batch transcription with its Arabic-English pack behind the speech-to-text port
(D-100: measured beside Groq, not a default).

`SpeechmaticsSTT` runs one batch job a clip by raw HTTPS (adapters/provider_http.py: no SDK, no
variable of its own read, no redirect followed), on the region `speechmatics.region` names
(`https://eu1.asr.api.speechmatics.com/v2` by default):

1. `POST /jobs`: the clip as WAV (`data_file`) and its config (`config`, JSON): a transcription
   in the language pack `ar_en`, Arabic with English, whatever language the request names, since
   the pack hears both; the `enhanced` operating point.
2. `GET /jobs/{id}` every `POLL_S` until the job is `done`; `rejected`, `deleted` or `expired`
   is a failure.
3. `GET /jobs/{id}/transcript?format=txt`: the text.
4. `DELETE /jobs/{id}`, best effort, so the job is not kept the 7 days Speechmatics keeps a
   finished one; a failed delete fails nothing.

A batch job queues, so it takes longer than one request: the whole job, every step above but the
delete, takes at most `speechmatics.job_timeout_s`, and its latency is measured, never assumed
(the bake-off reports it). The pack documents no language label or score, so the transcript's
`heard_language` and `language_probability` stay None; `language` is the request's. Its output
is data, never an instruction (docs/SECURITY.md, trust boundaries). Every failure is a
ProviderError naming no key, audio or transcript; a cancel stops the job's requests at once.
"""

from __future__ import annotations

import asyncio
import json
from typing import Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from t2_agentic_voice.adapters.provider_http import (
    AnswerError,
    given_key,
    http_client,
    http_failure,
    ok_status,
    provider_key,
)
from t2_agentic_voice.adapters.wav_files import wav_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.provider_keys import SpeechmaticsRegion, SpeechmaticsSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, DataFlow, Transcript

VENDOR: Final = "Speechmatics"
HOSTS: Final[dict[SpeechmaticsRegion, str]] = {
    "eu": "https://eu1.asr.api.speechmatics.com/v2",
    "us": "https://us1.asr.api.speechmatics.com/v2",
}
LANGUAGE_PACK: Final = "ar_en"
# How long the adapter waits between two reads of a job's status, in seconds.
POLL_S: Final = 0.5
# Each single request's own limit inside the job's, in seconds.
REQUEST_TIMEOUT_S: Final = 15.0
# Where Speechmatics processes and keeps batch jobs, from the provider guide's reading of its
# pages (2026-11-16).
DATA_FLOW: Final = DataFlow(
    provider="Speechmatics",
    processed_in="EU (eu1) by default, or US (us1), as speechmatics.region names",
    stored_in="the region's batch store, until the job is deleted",
    retention=(
        "a finished batch job is deleted after 7 days, and this adapter deletes each job once "
        "its transcript is read; no training unless the account opts in (off by default)"
    ),
)
_JobStatus = Literal["running", "done", "rejected", "deleted", "expired"]


class SpeechmaticsSTT:
    """Speech-to-text with Speechmatics' batch `ar_en` pack; a `SpeechToText`. `transport`
    replaces the HTTP transport (a test's fake one); `poll_s` the wait between status reads.
    Close it with `aclose()`."""

    name: str = "speechmatics"
    data_flow: DataFlow = DATA_FLOW

    def __init__(
        self,
        *,
        api_key: SecretStr,
        region: SpeechmaticsRegion = "eu",
        job_timeout_s: float = 60.0,
        poll_s: float = POLL_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = given_key(api_key, SpeechmaticsSettings, VENDOR)
        self._region: SpeechmaticsRegion = region
        self._base = HOSTS[region]
        self._job_timeout_s = job_timeout_s
        self._poll_s = poll_s
        timeout = min(REQUEST_TIMEOUT_S, job_timeout_s)
        self._http = http_client(timeout_s=timeout, transport=transport)

    @classmethod
    def from_settings(
        cls, settings: VoiceSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> SpeechmaticsSTT:
        """The adapter the settings describe: `speechmatics`' key, region and job timeout; a
        ConfigurationError naming `T2V_SPEECHMATICS__API_KEY` (under the settings' prefix)
        when no key is set."""
        group = settings.speechmatics
        return cls(
            api_key=provider_key(settings, group, VENDOR),
            region=group.region,
            job_timeout_s=group.job_timeout_s,
            transport=transport,
        )

    def __repr__(self) -> str:
        return f"SpeechmaticsSTT(region={self._region!r}, job_timeout_s={self._job_timeout_s!r})"

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        """What was said in `clip` (the port's `transcribe`; the module's docstring). `prompt`
        is not sent: the pack takes no prompt. Raises ProviderError on every failure, a job
        Speechmatics refused or lost and an answer it cannot read included."""
        headers = {"authorization": f"Bearer {self._api_key.get_secret_value()}"}
        job: list[str] = []
        failed: ProviderError | None = None
        text = ""
        try:
            async with asyncio.timeout(self._job_timeout_s):
                job.append(await self._submit(clip, headers))
                await self._finished(job[0], headers)
                text = await self._transcript(job[0], headers)
        except Exception as error:  # every failure, httpx's and the answers'; never a cancel
            failed = http_failure(self.name, error)
        for each in job:
            await self._delete(each, headers)
        if failed is not None:
            raise failed from None
        return Transcript(text=text.strip(), language=language or None, billed_seconds=clip.seconds)

    async def _submit(self, clip: AudioClip, headers: dict[str, str]) -> str:
        config = {
            "type": "transcription",
            "transcription_config": {"language": LANGUAGE_PACK, "operating_point": "enhanced"},
        }
        response = await self._http.post(
            f"{self._base}/jobs",
            data={"config": json.dumps(config)},
            files={"data_file": ("speech.wav", wav_of(clip), "audio/wav")},
            headers=headers,
        )
        return _Created.model_validate_json(ok_status(response).content).id

    async def _finished(self, job: str, headers: dict[str, str]) -> None:
        while True:
            response = await self._http.get(f"{self._base}/jobs/{job}", headers=headers)
            status = _Status.model_validate_json(ok_status(response).content).job.status
            if status == "done":
                return
            if status != "running":
                raise AnswerError(f"job_{status}")
            await asyncio.sleep(self._poll_s)

    async def _transcript(self, job: str, headers: dict[str, str]) -> str:
        response = await self._http.get(
            f"{self._base}/jobs/{job}/transcript", params={"format": "txt"}, headers=headers
        )
        try:
            return ok_status(response).content.decode("utf-8")
        except UnicodeDecodeError:  # it holds the transcript's bytes: not chained
            pass
        raise AnswerError("transcript_not_utf8")

    async def _delete(self, job: str, headers: dict[str, str]) -> None:
        """Delete the job, best effort: its failure fails nothing; a cancel still stops it."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_S):
                await self._http.delete(f"{self._base}/jobs/{job}", headers=headers)
        except Exception:  # noqa: S110 - a job left behind is deleted by Speechmatics in 7 days
            pass

    async def aclose(self) -> None:
        """Close the adapter's HTTP connections."""
        await self._http.aclose()


class _Created(BaseModel):
    """The answer to a job's upload, as far as the adapter reads it: an id that goes into the
    next requests' paths, so letters, digits, `_` and `-` only, never a path or a query."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class _Job(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    status: _JobStatus


class _Status(BaseModel):
    """The answer to a job's status read, as far as the adapter reads it."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    job: _Job
