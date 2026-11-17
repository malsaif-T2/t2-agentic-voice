"""ElevenLabsTTS against a fake ElevenLabs on httpx's MockTransport (nothing leaves the machine):
the streamed request, its raw PCM read in whole samples at the asked rate, the concurrency
headroom, the cut-short flag, each failure as a ProviderError showing no key or text, the
refusals made unsent, a cancel, the language check, and the composition root's choice of it
by `tts.provider` (D-114)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.elevenlabs_tts import ElevenLabsTTS
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import KEY as GROQ_KEY
from tests.t2_agentic_voice.adapters.provider_support import KEY, FakeProvider, Handler, raising
from tests.t2_agentic_voice.adapters.tts_support import silence, tone

TEXT = "These made-up words 4471 are spoken for the test."  # 49 characters
VOICE = "MadeUpVoice0123456789"
VOICES: dict[LanguageTag, TtsVoice] = {"en": TtsVoice(model="eleven_v4_turbo", voice=VOICE)}
SPEECH = silence(0.1) + tone(2.0)  # two seconds of speech after a tenth of silence
HEADROOM = {"current-concurrent-requests": "2", "maximum-concurrent-requests": "6"}


def streaming(pcm: bytes, *, pieces: int = 5, headers: dict[str, str] | None = None) -> Handler:
    """A handler that streams `pcm` in `pieces`, split anywhere (inside a sample too)."""

    async def body() -> AsyncIterator[bytes]:
        size = len(pcm) // pieces + 1
        for at in range(0, len(pcm), size):
            yield pcm[at : at + size]

    return lambda request: httpx.Response(200, content=body(), headers=headers or {})


def _tts(fake: FakeProvider, *, timeout_s: float = 6.0) -> ElevenLabsTTS:
    return ElevenLabsTTS(
        api_key=SecretStr(KEY), languages=VOICES, timeout_s=timeout_s, transport=fake.transport()
    )


def _take(fake: FakeProvider, text: str = TEXT, language: str = "en") -> list[AudioChunk]:
    async def go() -> list[AudioChunk]:
        tts = _tts(fake)
        try:
            return [chunk async for chunk in tts.synthesize(text, language=language)]
        finally:
            await tts.aclose()

    return asyncio.run(go())


def test_the_request_streams_raw_pcm_at_24_khz_in_the_clauses_language() -> None:
    fake = FakeProvider(streaming(SPEECH))
    _take(fake)
    (request,) = fake.requests
    assert request.method == "POST"
    assert str(request.url) == (
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/stream?output_format=pcm_24000"
    )
    assert request.headers["xi-api-key"] == KEY and "authorization" not in request.headers
    body = json.loads(request.content)
    assert body == {"text": TEXT, "model_id": "eleven_v4_turbo", "language_code": "en"}


def test_the_audio_comes_in_whole_samples_with_the_headroom_on_its_first_chunk() -> None:
    chunks = _take(FakeProvider(streaming(SPEECH, pieces=7, headers=HEADROOM)))
    assert b"".join(chunk.pcm16 for chunk in chunks) == SPEECH
    assert all(len(chunk.pcm16) % 2 == 0 and chunk.sample_rate == 24_000 for chunk in chunks)
    assert len(chunks) > 1 and chunks[0].remaining_requests == 4
    assert all(chunk.remaining_requests is None for chunk in chunks[1:])
    assert not any(chunk.cut_short for chunk in chunks)


def test_a_take_too_short_for_its_text_is_flagged_on_a_last_empty_chunk() -> None:
    chunks = _take(FakeProvider(streaming(tone(0.5))))
    assert chunks[-1].pcm16 == b"" and chunks[-1].cut_short


def test_a_take_with_no_audio_still_ends_with_one_chunk_carrying_its_headroom() -> None:
    (chunk,) = _take(FakeProvider(streaming(b"", headers=HEADROOM)))
    assert (chunk.pcm16, chunk.cut_short, chunk.remaining_requests) == (b"", True, 4)


def test_a_language_with_no_voice_and_a_text_over_the_limit_are_refused_unsent() -> None:
    fake = FakeProvider(streaming(SPEECH))
    with pytest.raises(ProviderError) as raised:
        _take(fake, language="ar-SA")
    assert raised.value.details == {"error": "no_voice"}
    with pytest.raises(ProviderError) as raised:
        _take(fake, text="x" * 10_001)
    assert raised.value.details == {"error": "too_long", "max_chars": 10_000}
    assert fake.requests == []
    tts = _tts(fake)
    assert (tts.max_chars("en"), tts.max_chars("ar")) == (10_000, 5_000)


FAILURES = [
    (lambda r: httpx.Response(401, json={"detail": {"message": TEXT}}), "rejected", False, 401),
    (lambda r: httpx.Response(429, json={"detail": TEXT}), "rate_limited", True, 429),
    (lambda r: httpx.Response(503, text=TEXT), "server_error", True, 503),
    (
        lambda r: httpx.Response(307, headers={"location": "https://x.example/"}),
        "rejected",
        False,
        307,
    ),
    (raising(httpx.ConnectError(f"{KEY} {TEXT}")), "connection_lost", True, None),
    (raising(httpx.ReadTimeout(f"{KEY} {TEXT}")), "timeout", True, None),
]


@pytest.mark.parametrize(("handler", "kind", "retryable", "status"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_or_text(
    handler: Handler,
    kind: str,
    retryable: bool,
    status: int | None,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider, the failure's class and the status, nothing else;
    a redirect is never followed, since it would carry the key to another host."""
    caplog.set_level(logging.DEBUG)
    fake = FakeProvider(handler)
    with pytest.raises(ProviderError) as raised:
        _take(fake)
    error = raised.value
    assert (error.kind, error.retryable) == (kind, retryable)
    assert error.details["provider"] == "elevenlabs" and error.details.get("status") == status
    assert (error.__cause__, error.__context__) == (None, None) and len(fake.requests) == 1
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, TEXT):
        assert holding(value, surfaces) == []


def test_a_cancel_stops_the_take_at_once() -> None:
    started = asyncio.Event()

    async def hang() -> AsyncIterator[bytes]:
        yield SPEECH[:4800]
        started.set()
        await asyncio.sleep(30)
        yield b""

    async def go() -> None:
        tts = _tts(FakeProvider(lambda request: httpx.Response(200, content=hang())))

        async def play() -> None:
            async for _ in tts.synthesize(TEXT, language="en"):
                pass

        task = asyncio.create_task(play())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await tts.aclose()

    asyncio.run(asyncio.wait_for(go(), 5))


def _check(handler: Handler) -> tuple[FakeProvider, object]:
    fake = FakeProvider(handler)

    async def go() -> object:
        tts = _tts(fake)
        try:
            return await tts.check_language("en")
        finally:
            await tts.aclose()

    return fake, asyncio.run(go())


def test_the_language_check_lists_the_models_and_returns_elevenlabs_time() -> None:
    listing = [{"model_id": "eleven_flash_v2_5"}, {"model_id": "eleven_v4_turbo", "x": 1}]
    date = {"date": "Tue, 17 Nov 2026 10:33:51 GMT"}
    fake, when = _check(lambda request: httpx.Response(200, json=listing, headers=date))
    (request,) = fake.requests
    assert (request.method, str(request.url)) == ("GET", "https://api.elevenlabs.io/v1/models")
    assert str(when) == "2026-11-17 10:33:51+00:00"
    with pytest.raises(ProviderError) as raised:
        _check(lambda request: httpx.Response(200, json=listing[:1]))
    assert raised.value.details == {"error": "model_not_listed", "model": "eleven_v4_turbo"}

    async def unset() -> None:
        tts = _tts(FakeProvider(streaming(b"")))
        try:
            await tts.check_language("ar")
        finally:
            await tts.aclose()

    with pytest.raises(ConfigurationError):
        asyncio.run(unset())


def test_tts_provider_picks_it_with_the_providers_default_voices_and_needs_its_key() -> None:
    keys = {"elevenlabs": {"api_key": KEY}, "groq": {"api_key": GROQ_KEY}}
    settings = VoiceSettings.model_validate(
        {"env": "test", "tts": {"provider": "elevenlabs"}, **keys}
    )
    tts = Providers.from_settings(settings).tts
    assert isinstance(tts, ElevenLabsTTS) and tts.name == "elevenlabs"
    assert {v.model for v in settings.tts.languages.values()} == {"eleven_v4_turbo"}
    bare = VoiceSettings.model_validate({"env": "test", "tts": {"provider": "elevenlabs"}})
    with pytest.raises(ConfigurationError) as raised:
        ElevenLabsTTS.from_settings(bare)
    assert raised.value.details == {"setting": "T2V_ELEVENLABS__API_KEY"}
    assert "tts.provider (groq" in raised.value.message
