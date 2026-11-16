"""ElevenLabsSTT against a fake ElevenLabs on httpx's MockTransport (nothing leaves the machine):
the request, the answer with its language and probability, the keyterms, each failure as a
ProviderError showing no key, audio or transcript, a timeout and a cancel, and the composition
root's choice of it by `stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText, Transcript

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

ANSWER = {"text": f"  {HEARD} ", "language_code": "ara", "language_probability": 0.97}


def _run(fake: FakeProvider, *, language: str | None, prompt: str | None) -> Transcript:
    async def go() -> Transcript:
        stt = ElevenLabsSTT.from_settings(keyed("elevenlabs"), transport=fake.transport())
        try:
            return await stt.transcribe(CLIP, language=language, prompt=prompt)
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_the_request_names_the_model_the_language_and_the_prompts_keyterms() -> None:
    fake = FakeProvider(answering(200, ANSWER))
    _run(fake, language="ar", prompt="Ole5, OTP , كلمة المرور,, Ole5")
    (request,) = fake.requests
    assert (request.method, str(request.url)) == (
        "POST",
        "https://api.elevenlabs.io/v1/speech-to-text",
    )
    assert request.headers["xi-api-key"] == KEY and "authorization" not in request.headers
    assert texts(request) == {
        "model_id": ["scribe_v3"],
        "tag_audio_events": ["false"],
        "timestamps_granularity": ["none"],
        "language_code": ["ar"],
        "keyterms": ["Ole5", "OTP", "كلمة المرور"],
    }
    ((_, headers, wav),) = [part for part in fields(request) if part[0] == "file"]
    assert headers["content-type"] == "audio/wav" and 'filename="speech.wav"' in str(headers)
    assert wav[:4] == b"RIFF" and len(wav) == 44 + len(CLIP.pcm16)


def test_with_no_language_and_no_prompt_scribe_detects_and_gets_no_keyterms() -> None:
    fake = FakeProvider(answering(200, ANSWER))
    _run(fake, language=None, prompt="")
    assert set(texts(fake.requests[0])) == {
        "model_id",
        "tag_audio_events",
        "timestamps_granularity",
    }


def test_the_keyterms_are_at_most_100_each_at_most_50_characters() -> None:
    terms = [f"term{i}" for i in range(130)] + ["x" * 51]
    fake = FakeProvider(answering(200, ANSWER))
    _run(fake, language="en", prompt=", ".join(["x" * 51, *terms]))
    sent = texts(fake.requests[0])["keyterms"]
    assert sent == [f"term{i}" for i in range(100)]


def test_the_answer_carries_the_language_heard_and_its_probability() -> None:
    fake = FakeProvider(answering(200, ANSWER))
    detected = _run(fake, language=None, prompt=None)
    named = _run(FakeProvider(answering(200, ANSWER)), language="en", prompt=None)
    assert detected == named.model_copy(update={"language": "ar"})
    assert (detected.text, detected.language, detected.heard_language) == (HEARD, "ar", "ar")
    assert (detected.language_probability, detected.billed_seconds) == (0.97, 1.0)
    assert (named.language, named.heard_language) == ("en", "ar")
    bare = _run(FakeProvider(answering(200, {"text": HEARD})), language=None, prompt=None)
    assert (bare.language, bare.heard_language, bare.language_probability) == (None, None, None)
    english = {"text": HEARD, "language_code": "eng", "language_probability": 0.5}
    assert _run(FakeProvider(answering(200, english)), language=None, prompt=None).language == "en"


FAILURES = [
    (answering(401, {"detail": {"message": HEARD, "key": KEY}}), "rejected", False, None, 401),
    (answering(422, {"detail": HEARD}), "rejected", False, None, 422),
    (answering(307, b"", {"location": "https://elsewhere.example/"}), "rejected", False, None, 307),
    (answering(429, {"detail": HEARD}, {"retry-after": "2"}), "rate_limited", True, 2.0, 429),
    (answering(408, {"detail": HEARD}), "timeout", True, None, 408),
    (answering(503, {"detail": HEARD}), "server_error", True, None, 503),
    (answering(200, f"{{{HEARD}".encode()), "server_error", False, None, None),
    (
        answering(200, {"text": HEARD, "language_probability": 1.5}),
        "server_error",
        False,
        None,
        None,
    ),
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
    a redirect is never followed, since it would carry the key to another host."""
    caplog.set_level(logging.DEBUG)
    fake = FakeProvider(handler)
    with pytest.raises(ProviderError) as raised:
        _run(fake, language="ar", prompt="Ole5")
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retryable, delay)
    assert error.details["provider"] == "elevenlabs" and error.details.get("status") == status
    assert (error.__cause__, error.__context__) == (None, None)
    assert len(fake.requests) == 1
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    audio = CLIP.pcm16[:64].hex()
    for value in (KEY, HEARD, audio):
        assert holding(value, surfaces) == []


def test_a_request_past_its_timeout_is_a_timeout() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=ANSWER)

    async def go() -> None:
        stt = ElevenLabsSTT(
            api_key=SecretStr(KEY), timeout_s=0.05, transport=httpx.MockTransport(slow)
        )
        try:
            await stt.transcribe(CLIP, language="ar", prompt=None)
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)


def test_a_cancel_stops_the_request_at_once() -> None:
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(30)
        raise AssertionError("never answered")

    async def go() -> None:
        stt = ElevenLabsSTT(
            api_key=SecretStr(KEY), timeout_s=60, transport=httpx.MockTransport(hang)
        )
        task = asyncio.create_task(stt.transcribe(CLIP, language=None, prompt=None))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await stt.aclose()

    asyncio.run(asyncio.wait_for(go(), 5))


def test_with_no_key_elevenlabs_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "elevenlabs"}})
    for build in (ElevenLabsSTT.from_settings, Providers.speech_to_text):
        with pytest.raises(ConfigurationError) as raised:
            build(settings)
        assert raised.value.details == {"setting": "T2V_ELEVENLABS__API_KEY"}
        assert "T2V_ELEVENLABS__API_KEY_FILE" in raised.value.message


@pytest.mark.parametrize("bad", ["  ", f"{KEY} x", f"{KEY}\nx"])
def test_a_key_given_in_code_is_held_to_the_settings_rules(bad: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        ElevenLabsSTT(api_key=SecretStr(bad), timeout_s=1)
    assert raised.value.details == {"setting": "T2V_ELEVENLABS__API_KEY"}
    assert holding(KEY, shown(raised.value)) == []


def test_elevenlabs_is_the_default_and_groq_is_picked_by_name() -> None:
    """D-105: Scribe v3 is the default; Whisper, the fallback, is chosen by `stt.provider`."""
    chosen = Providers.speech_to_text(keyed("elevenlabs"))
    default = Providers.speech_to_text(
        VoiceSettings.model_validate(
            {"env": "test", "groq": {"api_key": KEY}, "stt": {"provider": "groq"}}
        )
    )
    assert isinstance(chosen, ElevenLabsSTT) and isinstance(default, GroqSTT)
    port: SpeechToText = chosen  # the port, as mypy reads it
    assert port is chosen
    assert (chosen.name, chosen.data_flow.provider) == ("elevenlabs", "ElevenLabs")
    assert KEY not in repr(chosen)
    asyncio.run(chosen.aclose())
    asyncio.run(default.aclose())
