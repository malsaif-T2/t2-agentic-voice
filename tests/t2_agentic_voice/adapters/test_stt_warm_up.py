"""The speech-to-text adapters' warm request (the `WarmUp` port, domain/ports/connection_warmth.py;
TD-089): ElevenLabs' and Groq's each one GET of the provider's model list, which costs nothing,
on the adapter's own client, with its key alone; a failure a ProviderError that shows no key. On
fake transports; nothing leaves the machine."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.connection_warmth import WarmUp

from tests.t2_agentic_voice.adapters import groq_support
from tests.t2_agentic_voice.adapters.groq_support import FakeGroq, groq_settings
from tests.t2_agentic_voice.adapters.provider_support import (
    KEY,
    FakeProvider,
    answering,
    keyed,
    raising,
)

MODELS = {"object": "list", "data": []}


def _eleven(fake: FakeProvider) -> ElevenLabsSTT:
    return ElevenLabsSTT.from_settings(keyed("elevenlabs"), transport=fake.transport())


def test_elevenlabs_warms_with_one_get_of_its_model_list() -> None:
    fake = FakeProvider(answering(200, [{"model_id": "scribe_v3"}]))
    stt = _eleven(fake)
    assert isinstance(stt, WarmUp)

    async def run() -> None:
        await stt.warm_up()
        await stt.aclose()

    asyncio.run(run())
    (request,) = fake.requests
    assert (request.method, str(request.url)) == ("GET", "https://api.elevenlabs.io/v1/models")
    assert request.headers["xi-api-key"] == KEY and request.content == b""


@pytest.mark.parametrize(
    "handler",
    [answering(401, {"detail": KEY}), raising(httpx.ConnectError(KEY))],
    ids=["refused", "unreachable"],
)
def test_a_failed_elevenlabs_warm_up_is_a_provider_error_showing_no_key(handler: object) -> None:
    stt = _eleven(FakeProvider(handler))  # type: ignore[arg-type]

    async def run() -> None:
        try:
            await stt.warm_up()
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(run())
    assert raised.value.details["provider"] == "elevenlabs"
    assert KEY not in repr(raised.value) + repr(raised.value.details)


def test_groq_whisper_warms_with_one_bodiless_get_of_its_model_list() -> None:
    fake = FakeGroq(httpx.Response(200, json=MODELS))
    stt = GroqSTT.from_settings(groq_settings(), transport=fake)
    assert isinstance(stt, WarmUp)

    async def run() -> None:
        await stt.warm_up()
        await stt.aclose()

    asyncio.run(run())
    (request,) = fake.requests
    assert (request.method, request.url.path, request.content) == ("GET", "/openai/v1/models", b"")
    assert request.headers["authorization"] == f"Bearer {groq_support.KEY}"
    assert "content-type" not in request.headers


def test_a_failed_groq_whisper_warm_up_is_a_provider_error_showing_no_key() -> None:
    fake = FakeGroq(httpx.Response(503, json={"error": {"message": groq_support.KEY}}))
    stt = GroqSTT.from_settings(groq_settings(), transport=fake)

    async def run() -> None:
        try:
            await stt.warm_up()
        finally:
            await stt.aclose()

    with pytest.raises(ProviderError) as raised:
        asyncio.run(run())
    assert (raised.value.kind, raised.value.retryable) == ("server_error", True)
    assert groq_support.KEY not in repr(raised.value) + repr(raised.value.details)
