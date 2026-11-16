"""CohereSTT against a fake Cohere on httpx's MockTransport (nothing leaves the machine): the
request with its language always named, the answer, each failure as a ProviderError showing no
key, audio or transcript, a timeout and a cancel, and the composition root's choice of it by
`stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.cohere_stt import CohereSTT
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
    Handler,
    answering,
    fields,
    keyed,
    raising,
    texts,
)

ANSWER = {"text": f"  {HEARD} ", "meta": {"billed_units": {"seconds": 1}}}


def _run(fake: FakeProvider, *, language: str | None, prompt: str | None = None) -> Transcript:
    async def go() -> Transcript:
        stt = CohereSTT.from_settings(keyed("cohere"), transport=fake.transport())
        try:
            return await stt.transcribe(CLIP, language=language, prompt=prompt)
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_the_request_names_the_model_and_the_language_and_sends_no_prompt() -> None:
    fake = FakeProvider(answering(200, ANSWER))
    _run(fake, language="en", prompt="Ole5, OTP")
    (request,) = fake.requests
    assert (request.method, str(request.url)) == (
        "POST",
        "https://api.cohere.com/v2/audio/transcriptions",
    )
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert texts(request) == {"model": ["cohere-transcribe-arabic-07-2026"], "language": ["en"]}
    ((_, headers, wav),) = [part for part in fields(request) if part[0] == "file"]
    assert headers["content-type"] == "audio/wav" and 'filename="speech.wav"' in str(headers)
    assert wav[:4] == b"RIFF" and len(wav) == 44 + len(CLIP.pcm16)


def test_with_no_language_named_arabic_is_sent_since_the_model_detects_none() -> None:
    fake = FakeProvider(answering(200, ANSWER))
    transcript = _run(fake, language=None)
    assert texts(fake.requests[0])["language"] == ["ar"]
    assert (transcript.text, transcript.language, transcript.billed_seconds) == (HEARD, "ar", 1.0)
    assert (transcript.heard_language, transcript.language_probability) == (None, None)


FAILURES = [
    (answering(401, {"message": HEARD, "key": KEY}), "rejected", False, None, 401),
    (answering(307, b"", {"location": "https://elsewhere.example/"}), "rejected", False, None, 307),
    (answering(429, {"message": HEARD}, {"retry-after": "12"}), "rate_limited", True, 12.0, 429),
    (answering(500, {"message": HEARD}), "server_error", True, None, 500),
    (answering(200, f"{{{HEARD}".encode()), "server_error", False, None, None),
    (answering(200, {"transcript": HEARD}), "server_error", False, None, None),
    (raising(httpx.ConnectError(f"{KEY} {HEARD}")), "connection_lost", True, None, None),
    (raising(httpx.ReadTimeout(f"{KEY} {HEARD}")), "timeout", True, None, None),
]


@pytest.mark.parametrize(("handler", "kind", "retryable", "delay", "status"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_audio_or_transcript(
    handler: Handler,
    kind: str,
    retryable: bool,
    delay: float | None,
    status: int | None,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider, the failure's class and the status, nothing else;
    a redirect is never followed, and a rate limit carries its `retry-after` for the pacer."""
    caplog.set_level(logging.DEBUG)
    fake = FakeProvider(handler)
    with pytest.raises(ProviderError) as raised:
        _run(fake, language="ar")
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retryable, delay)
    assert error.details["provider"] == "cohere" and error.details.get("status") == status
    assert (error.__cause__, error.__context__) == (None, None)
    assert len(fake.requests) == 1
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, HEARD, CLIP.pcm16[:64].hex()):
        assert holding(value, surfaces) == []


def test_a_request_past_its_timeout_is_a_timeout_and_a_cancel_stops_it_at_once() -> None:
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(30)
        raise AssertionError("never answered")

    async def timed_out() -> None:
        stt = CohereSTT(api_key=SecretStr(KEY), timeout_s=0.05, transport=httpx.MockTransport(hang))
        try:
            await stt.transcribe(CLIP, language="ar", prompt=None)
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(timed_out())
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)

    async def cancelled() -> None:
        started.clear()
        stt = CohereSTT(api_key=SecretStr(KEY), timeout_s=60, transport=httpx.MockTransport(hang))
        task = asyncio.create_task(stt.transcribe(CLIP, language=None, prompt=None))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await stt.aclose()

    asyncio.run(asyncio.wait_for(cancelled(), 5))


def test_with_no_key_cohere_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "cohere"}})
    for build in (CohereSTT.from_settings, Providers.speech_to_text):
        with pytest.raises(ConfigurationError) as raised:
            build(settings)
        assert raised.value.details == {"setting": "T2V_COHERE__API_KEY"}
        assert "T2V_COHERE__API_KEY_FILE" in raised.value.message


@pytest.mark.parametrize("bad", ["  ", f"{KEY} x", f"{KEY}\nx"])
def test_a_key_given_in_code_is_held_to_the_settings_rules(bad: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        CohereSTT(api_key=SecretStr(bad), timeout_s=1)
    assert raised.value.details == {"setting": "T2V_COHERE__API_KEY"}
    assert holding(KEY, shown(raised.value)) == []


def test_stt_provider_cohere_picks_the_adapter() -> None:
    chosen = Providers.speech_to_text(keyed("cohere", provider="cohere"))
    assert isinstance(chosen, CohereSTT)
    assert (chosen.name, chosen.data_flow.provider) == ("cohere", "Cohere")
    assert KEY not in repr(chosen)
    asyncio.run(chosen.aclose())
