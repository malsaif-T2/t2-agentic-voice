"""SpeechmaticsSTT against a fake Speechmatics on httpx's MockTransport (nothing leaves the
machine): the job's upload, its polls, its transcript and its delete; each failure as a
ProviderError showing no key, audio or transcript; a job id that is not an id refused; the job's
timeout; and the composition root's choice of it by `stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.speechmatics_stt import SpeechmaticsSTT
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.provider_keys import SpeechmaticsRegion
from t2_agentic_voice.domain.ports.speech_to_text import Transcript

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.provider_support import (
    CLIP,
    HEARD,
    KEY,
    FakeProvider,
    fields,
    keyed,
    texts,
)

EU = "https://eu1.asr.api.speechmatics.com/v2"


def _speechmatics(
    statuses: list[str], *, job: str = "job_42", transcript: bytes = HEARD.encode()
) -> FakeProvider:
    """A fake that takes a job, reports `statuses` one poll each, then gives `transcript`."""
    left = list(statuses)

    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v2/jobs":
            return httpx.Response(201, json={"id": job})
        if request.method == "GET" and path == f"/v2/jobs/{job}":
            return httpx.Response(200, json={"job": {"id": job, "status": left.pop(0)}})
        if request.method == "GET" and path == f"/v2/jobs/{job}/transcript":
            return httpx.Response(200, content=transcript)
        if request.method == "DELETE":
            return httpx.Response(200, json={"job": {"id": job}})
        return httpx.Response(404, json={"detail": HEARD})

    return FakeProvider(answer)


def _run(
    fake: FakeProvider, *, language: str | None = "ar", region: SpeechmaticsRegion = "eu"
) -> Transcript:
    async def go() -> Transcript:
        stt = SpeechmaticsSTT(
            api_key=SecretStr(KEY), region=region, poll_s=0, transport=fake.transport()
        )
        try:
            return await stt.transcribe(CLIP, language=language, prompt="Ole5, OTP")
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_a_clip_is_one_job_uploaded_polled_read_and_deleted() -> None:
    fake = _speechmatics(["running", "running", "done"])
    transcript = _run(fake)
    calls = [(r.method, str(r.url)) for r in fake.requests]
    assert calls == [
        ("POST", f"{EU}/jobs"),
        ("GET", f"{EU}/jobs/job_42"),
        ("GET", f"{EU}/jobs/job_42"),
        ("GET", f"{EU}/jobs/job_42"),
        ("GET", f"{EU}/jobs/job_42/transcript?format=txt"),
        ("DELETE", f"{EU}/jobs/job_42"),
    ]
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in fake.requests)
    upload = fake.requests[0]
    config = json.loads(texts(upload)["config"][0])
    assert config == {
        "type": "transcription",
        "transcription_config": {"language": "ar_en", "operating_point": "enhanced"},
    }
    ((_, headers, wav),) = [part for part in fields(upload) if part[0] == "data_file"]
    assert headers["content-type"] == "audio/wav" and wav[:4] == b"RIFF"
    assert b"Ole5" not in upload.content  # the pack takes no prompt
    assert transcript == Transcript(text=HEARD, language="ar", billed_seconds=1.0)


def test_the_us_region_and_no_language_named() -> None:
    fake = _speechmatics(["done"])
    transcript = _run(fake, language=None, region="us")
    assert str(fake.requests[0].url) == "https://us1.asr.api.speechmatics.com/v2/jobs"
    assert (transcript.language, transcript.heard_language, transcript.language_probability) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("fake", "reason", "deletes"),
    [
        (_speechmatics(["running", "rejected"]), "job_rejected", 1),
        (_speechmatics(["expired"]), "job_expired", 1),
        (_speechmatics(["done"], transcript=b"\xff" + HEARD.encode()), "transcript_not_utf8", 1),
        (_speechmatics(["done"], job="../../jobs?x=1"), "ValidationError", 0),
        (_speechmatics(["unknown"]), "ValidationError", 1),
    ],
)
def test_a_job_that_fails_is_a_provider_error_and_is_still_deleted(
    fake: FakeProvider,
    reason: str,
    deletes: int,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A job id that is not an id never goes into a path: the upload's answer is refused, and
    there is no job to delete."""
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as raised:
        _run(fake)
    error = raised.value
    assert (error.kind, error.retryable, error.details["error"]) == ("server_error", False, reason)
    assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, HEARD, CLIP.pcm16[:64].hex()):
        assert holding(value, surfaces) == []
    assert [r.method for r in fake.requests].count("DELETE") == deletes
    assert all("?x=1" not in str(r.url) for r in fake.requests)


@pytest.mark.parametrize(("status", "kind"), [(401, "rejected"), (429, "rate_limited")])
def test_a_refused_upload_is_a_provider_error_naming_its_status(status: int, kind: str) -> None:
    fake = FakeProvider(lambda request: httpx.Response(status, json={"detail": HEARD, "k": KEY}))
    with pytest.raises(ProviderError) as raised:
        _run(fake)
    assert (raised.value.kind, raised.value.details["status"]) == (kind, status)
    assert [r.method for r in fake.requests] == ["POST"]  # no job, nothing to delete
    assert holding(KEY, shown(raised.value)) == [] and holding(HEARD, shown(raised.value)) == []


def test_a_job_past_its_timeout_is_a_timeout_and_is_deleted() -> None:
    fake = _speechmatics(["running"] * 10_000)

    async def go() -> None:
        stt = SpeechmaticsSTT(
            api_key=SecretStr(KEY), job_timeout_s=0.2, poll_s=0.01, transport=fake.transport()
        )
        try:
            await stt.transcribe(CLIP, language="ar", prompt=None)
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)
    assert fake.requests[-1].method == "DELETE"


def test_with_no_key_speechmatics_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "speechmatics"}})
    with pytest.raises(ConfigurationError) as raised:
        Providers.speech_to_text(settings)
    assert raised.value.details == {"setting": "T2V_SPEECHMATICS__API_KEY"}


def test_stt_provider_picks_speechmatics_with_its_region_and_job_timeout() -> None:
    settings = keyed("speechmatics", provider="speechmatics")
    settings = settings.model_copy(
        update={"speechmatics": settings.speechmatics.model_copy(update={"region": "us"})}
    )
    chosen = Providers.speech_to_text(settings)
    assert isinstance(chosen, SpeechmaticsSTT)
    assert repr(chosen) == "SpeechmaticsSTT(region='us', job_timeout_s=60.0)"
    assert (chosen.name, chosen.data_flow.provider) == ("speechmatics", "Speechmatics")
    asyncio.run(chosen.aclose())
