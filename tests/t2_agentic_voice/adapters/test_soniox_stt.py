"""SonioxSTT against a fake Soniox on httpx's MockTransport (nothing leaves the machine): the
file's upload, the job's start with its languages and terms, its polls, its transcript with the
language heard, and both deletes; each failure as a ProviderError showing no key, audio or
transcript; an id that is not an id refused; the job's timeout; and the composition root's
choice of it by `stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.soniox_stt import SonioxSTT
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import Transcript

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.provider_support import (
    CLIP,
    HEARD,
    KEY,
    FakeProvider,
    fields,
    keyed,
)

API = "https://api.soniox.com/v1"
WORDS = {
    "text": f" {HEARD} ",
    "tokens": [
        {"text": "made-up caller", "language": "en"},
        {"text": " كلمة المرور الطويلة جدا", "language": "ar"},
    ],
}


def _soniox(
    statuses: list[str],
    *,
    file: str = "file_7",
    job: str = "job_9",
    transcript: object = WORDS,
    failing: str = "",
) -> FakeProvider:
    """A fake that takes a file and a job, reports `statuses` one poll each, then gives
    `transcript`; the request whose method and path are `failing` answers 500."""
    left = list(statuses)

    def answer(request: httpx.Request) -> httpx.Response:
        route = f"{request.method} {request.url.path}"
        if route == failing:
            return httpx.Response(500, json={"message": HEARD})
        if route == "POST /v1/files":
            return httpx.Response(201, json={"id": file})
        if route == "POST /v1/transcriptions":
            return httpx.Response(201, json={"id": job, "status": "queued"})
        if route == f"GET /v1/transcriptions/{job}":
            return httpx.Response(200, json={"id": job, "status": left.pop(0)})
        if route == f"GET /v1/transcriptions/{job}/transcript":
            return httpx.Response(200, json=transcript)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"message": HEARD})

    return FakeProvider(answer)


def _run(
    fake: FakeProvider, *, language: str | None = "ar", prompt: str | None = None
) -> Transcript:
    async def go() -> Transcript:
        stt = SonioxSTT(api_key=SecretStr(KEY), poll_s=0, transport=fake.transport())
        try:
            return await stt.transcribe(CLIP, language=language, prompt=prompt)
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_a_clip_is_one_file_and_one_job_read_then_both_deleted() -> None:
    fake = _soniox(["queued", "processing", "completed"])
    transcript = _run(fake, language="en", prompt="Ole5, OTP, ,Ole5")
    calls = [(r.method, str(r.url)) for r in fake.requests]
    assert calls == [
        ("POST", f"{API}/files"),
        ("POST", f"{API}/transcriptions"),
        *[("GET", f"{API}/transcriptions/job_9")] * 3,
        ("GET", f"{API}/transcriptions/job_9/transcript"),
        ("DELETE", f"{API}/transcriptions/job_9"),
        ("DELETE", f"{API}/files/file_7"),
    ]
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in fake.requests)
    ((name, headers, wav),) = fields(fake.requests[0])
    assert (name, headers["content-type"], wav[:4]) == ("file", "audio/wav", b"RIFF")
    assert json.loads(fake.requests[1].content) == {
        "model": "stt-async-v6",
        "file_id": "file_7",
        "language_hints": ["en", "ar"],
        "language_hints_strict": True,
        "enable_language_identification": True,
        "context": {"terms": ["Ole5", "OTP"]},
    }
    assert (transcript.text, transcript.language, transcript.heard_language) == (HEARD, "en", "ar")
    assert (transcript.language_probability, transcript.billed_seconds) == (None, 1.0)


def test_with_no_language_named_the_language_heard_is_the_transcripts() -> None:
    fake = _soniox(["completed"])
    transcript = _run(fake, language=None)
    sent = json.loads(fake.requests[1].content)
    assert sent["language_hints"] == ["ar", "en"] and "context" not in sent
    assert (transcript.language, transcript.heard_language) == ("ar", "ar")
    bare = _run(_soniox(["completed"], transcript={"text": HEARD}), language=None)
    assert (bare.language, bare.heard_language) == (None, None)


FAILURES = [
    (_soniox(["error"]), "server_error", False, "job_error", 2),
    (_soniox(["queued", "done?"]), "server_error", False, "ValidationError", 2),
    (_soniox([], job="../files/x"), "server_error", False, "ValidationError", 1),
    (_soniox([], file="a/b"), "server_error", False, "ValidationError", 0),
    (
        _soniox(["completed"], transcript={"words": HEARD}),
        "server_error",
        False,
        "ValidationError",
        2,
    ),
    (_soniox([], failing="POST /v1/files"), "server_error", True, "HTTPStatusError", 0),
    (_soniox([], failing="POST /v1/transcriptions"), "server_error", True, "HTTPStatusError", 1),
]


@pytest.mark.parametrize(("fake", "kind", "retryable", "error", "deletes"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_audio_or_transcript(
    fake: FakeProvider,
    kind: str,
    retryable: bool,
    error: str,
    deletes: int,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19, and what was made is still deleted (`deletes`: the file, then the job too); an id
    that is not an id is never put into a path."""
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as raised:
        _run(fake, prompt="Ole5")
    failure = raised.value
    assert (failure.kind, failure.retryable) == (kind, retryable)
    assert failure.details["provider"] == "soniox" and failure.details["error"] == error
    assert (failure.__cause__, failure.__context__) == (None, None)
    paths = [r.url.path for r in fake.requests]
    assert not [path for path in paths if ".." in path or "a/b" in path]
    assert len([r for r in fake.requests if r.method == "DELETE"]) == deletes
    surfaces = shown(failure, caplog=caplog, capsys=capsys)
    for value in (KEY, HEARD, CLIP.pcm16[:64].hex()):
        assert holding(value, surfaces) == []


def test_a_job_past_its_timeout_is_a_timeout_and_its_file_is_still_deleted() -> None:
    fake = _soniox(["queued"] * 10_000)

    async def go() -> None:
        stt = SonioxSTT(
            api_key=SecretStr(KEY), job_timeout_s=0.2, poll_s=0.01, transport=fake.transport()
        )
        try:
            await stt.transcribe(CLIP, language="ar", prompt=None)
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)
    deleted = [r.url.path for r in fake.requests if r.method == "DELETE"]
    assert deleted == ["/v1/transcriptions/job_9", "/v1/files/file_7"]


def test_a_failed_delete_fails_nothing() -> None:
    fake = _soniox(["completed"], failing="DELETE /v1/files/file_7")
    assert _run(fake).text == HEARD


def test_with_no_key_soniox_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "soniox"}})
    for build in (SonioxSTT.from_settings, Providers.speech_to_text):
        with pytest.raises(ConfigurationError) as raised:
            build(settings)
        assert raised.value.details == {"setting": "T2V_SONIOX__API_KEY"}
        assert "T2V_SONIOX__API_KEY_FILE" in raised.value.message


@pytest.mark.parametrize("bad", ["  ", f"{KEY} x", f"{KEY}\nx"])
def test_a_key_given_in_code_is_held_to_the_settings_rules(bad: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        SonioxSTT(api_key=SecretStr(bad))
    assert raised.value.details == {"setting": "T2V_SONIOX__API_KEY"}
    assert holding(KEY, shown(raised.value)) == []


def test_stt_provider_picks_soniox_with_its_job_timeout() -> None:
    settings = keyed("soniox", provider="soniox")
    settings = settings.model_copy(
        update={"soniox": settings.soniox.model_copy(update={"job_timeout_s": 30.0})}
    )
    chosen = Providers.speech_to_text(settings)
    assert isinstance(chosen, SonioxSTT)
    assert repr(chosen) == "SonioxSTT(model='stt-async-v6', job_timeout_s=30.0)"
    assert (chosen.name, chosen.data_flow.provider) == ("soniox", "Soniox")
    asyncio.run(chosen.aclose())
