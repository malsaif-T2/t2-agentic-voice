"""TelnyxSTT against a fake Telnyx (nothing leaves the machine): HUMAIN's engine on a fake
WebSocket (the handshake, the audio and its tail, the finals read until a close or a quiet
socket) and the batch models on httpx's MockTransport; each failure as a ProviderError showing
no key, audio or transcript, a timeout and a cancel, and the composition root's choice of it by
`stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.telnyx_stt import TelnyxSTT
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
    FakeSocket,
    Message,
    Reply,
    answering,
    closed,
    handshake_refused,
    keyed,
    refusing,
    sent_audio,
    sent_json,
    texts,
)

CLOSE_STREAM = json.dumps({"type": "CloseStream"})


def _frame(text: str, *, final: bool = True, confidence: float | None = 0.9) -> str:
    return json.dumps({"transcript": text, "is_final": final, "confidence": confidence})


def _telnyx(*replies: Reply) -> FakeSocket:
    """A Telnyx that answers the turn's CloseStream with `replies`."""
    return FakeSocket(lambda message: list(replies) if message == CLOSE_STREAM else [])


def _settings(**telnyx: object) -> VoiceSettings:
    return VoiceSettings.model_validate(
        {"env": "test", "telnyx": {"api_key": KEY, "quiet_s": 0.05, **telnyx}}
    )


def _run(socket: FakeSocket, *, language: str | None, **telnyx: object) -> Transcript:
    async def go() -> Transcript:
        stt = TelnyxSTT.from_settings(_settings(**telnyx), opener=socket.opener)
        try:
            return await stt.transcribe(CLIP, language=language, prompt="Ole5, OTP")
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_humains_engine_hears_the_turn_on_telnyxs_websocket() -> None:
    socket = _telnyx(
        _frame("ignored", final=False), _frame(f" {HEARD} "), _frame("ok", confidence=0.7), closed()
    )
    heard = _run(socket, language="ar")
    ((url, headers, timeout_s),) = socket.opened
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "wss",
        "api.telnyx.com",
        "/v2/speech-to-text/transcription",
    )
    assert parse_qs(parts.query) == {
        "transcription_engine": ["Humain"],
        "model": ["humain/realtime"],
        "input_format": ["linear16"],
        "sample_rate": ["16000"],
        "language": ["ar"],
    }
    assert headers == {"authorization": f"Bearer {KEY}"} and timeout_s == 10.0
    assert sent_audio(socket) == CLIP.pcm16 + bytes(32_000)  # a second of silence after it
    assert {len(m) for m in socket.sent if isinstance(m, bytes)} == {3200}
    assert socket.sent[-1] == CLOSE_STREAM and sent_json(socket) == [{"type": "CloseStream"}]
    assert (heard.text, heard.language, heard.heard_language) == (f"{HEARD} ok", "ar", None)
    assert heard.confidence == pytest.approx(0.8) and heard.billed_seconds == 2.0
    assert socket.closes == 1


def test_with_no_language_the_engine_code_switches_and_a_quiet_socket_ends_the_turn() -> None:
    socket = _telnyx(_frame(HEARD, confidence=None))  # Telnyx never closes
    heard = _run(socket, language=None)
    assert parse_qs(urlsplit(socket.opened[0][0]).query)["language"] == ["codeswitch"]
    assert (heard.text, heard.language, heard.confidence) == (HEARD, None, None)
    silent = _run(_telnyx(closed()), language="en")
    assert (silent.text, silent.confidence) == ("", None)


def test_a_batch_model_goes_to_telnyxs_transcription_endpoint() -> None:
    fake = FakeProvider(answering(200, {"text": f" {HEARD} ", "duration": 1.0}))

    async def go(language: str | None) -> Transcript:
        settings = _settings(stt_model="deepgram/nova-3")
        stt = TelnyxSTT.from_settings(settings, transport=fake.transport())
        try:
            return await stt.transcribe(CLIP, language=language, prompt="Ole5")
        finally:
            await stt.aclose()

    heard = asyncio.run(go("ar"))
    (request,) = fake.requests
    assert (request.method, str(request.url)) == (
        "POST",
        "https://api.telnyx.com/v2/ai/audio/transcriptions",
    )
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert texts(request) == {
        "model": ["deepgram/nova-3"],
        "response_format": ["json"],
        "language": ["ar"],
    }
    assert (heard.text, heard.language, heard.billed_seconds) == (HEARD, "ar", 1.0)
    asyncio.run(go(None))
    assert "language" not in texts(fake.requests[1])


ERROR_FRAME = json.dumps({"errors": [{"detail": HEARD, "key": KEY}]})
STREAM_FAILURES = [
    (refusing(handshake_refused(401)), "rejected", False, None, 401),
    (refusing(handshake_refused(429, "2")), "rate_limited", True, 2.0, 429),
    (refusing(handshake_refused(503)), "server_error", True, None, 503),
    (refusing(OSError(f"{KEY} {HEARD}")), "connection_lost", True, None, None),
    (_telnyx(ERROR_FRAME).opener, "server_error", False, None, None),
    (
        _telnyx(json.dumps({"type": "error", "error": HEARD})).opener,
        "server_error",
        False,
        None,
        None,
    ),
    (_telnyx(f"{{{HEARD}").opener, "server_error", False, None, None),
    (_telnyx(_frame(HEARD, confidence=1.5)).opener, "server_error", False, None, None),
    (_telnyx(closed(1008)).opener, "rejected", False, None, None),
    (_telnyx(closed(1011)).opener, "connection_lost", True, None, None),
]


@pytest.mark.parametrize(("opener", "kind", "retryable", "delay", "status"), STREAM_FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_audio_or_transcript(
    opener: object,
    kind: str,
    retryable: bool,
    delay: float | None,
    status: int | None,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider, the failure's class, a status or a close code."""
    caplog.set_level(logging.DEBUG)

    async def go() -> None:
        stt = TelnyxSTT.from_settings(_settings(), opener=opener)  # type: ignore[arg-type]
        await stt.transcribe(CLIP, language="ar", prompt=None)

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retryable, delay)
    assert error.details["provider"] == "telnyx" and error.details.get("status") == status
    assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, HEARD, CLIP.pcm16[:64].hex()):
        assert holding(value, surfaces) == []


def test_a_batch_failure_is_a_provider_error_showing_nothing_it_held() -> None:
    fake = FakeProvider(answering(401, {"detail": HEARD, "key": KEY}))

    async def go() -> None:
        settings = _settings(stt_model="openai/whisper-large-v3-turbo")
        stt = TelnyxSTT.from_settings(settings, transport=fake.transport())
        await stt.transcribe(CLIP, language=None, prompt=None)

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    assert (raised.value.kind, raised.value.details.get("status")) == ("rejected", 401)
    assert holding(KEY, shown(raised.value)) == holding(HEARD, shown(raised.value)) == []


def test_a_turn_past_its_timeout_is_a_timeout_and_a_cancel_stops_it_at_once() -> None:
    def never(message: Message) -> list[Reply]:
        return []

    hung = FakeSocket(never)
    with pytest.raises(ProviderError) as raised:
        _run(hung, language="ar", turn_timeout_s=0.05, quiet_s=5)
    assert (raised.value.kind, raised.value.retryable, hung.closes) == ("timeout", True, 1)

    async def cancelled() -> None:
        socket = FakeSocket(never)
        stt = TelnyxSTT.from_settings(_settings(quiet_s=10), opener=socket.opener)
        task = asyncio.create_task(stt.transcribe(CLIP, language=None, prompt=None))
        while not socket.sent or socket.sent[-1] != CLOSE_STREAM:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert socket.closes == 1

    asyncio.run(asyncio.wait_for(cancelled(), 5))


def test_with_no_key_telnyx_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "telnyx"}})
    for build in (TelnyxSTT.from_settings, Providers.speech_to_text):
        with pytest.raises(ConfigurationError) as raised:
            build(settings)
        assert raised.value.details == {"setting": "T2V_TELNYX__API_KEY"}
        assert "T2V_TELNYX__API_KEY_FILE" in raised.value.message


@pytest.mark.parametrize("bad", ["  ", f"{KEY} x", f"{KEY}\nx"])
def test_a_key_given_in_code_is_held_to_the_settings_rules(bad: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        TelnyxSTT(api_key=SecretStr(bad), timeout_s=1)
    assert raised.value.details == {"setting": "T2V_TELNYX__API_KEY"}
    assert holding(KEY, shown(raised.value)) == []


def test_stt_provider_picks_telnyx() -> None:
    chosen = Providers.speech_to_text(keyed("telnyx", provider="telnyx"))
    assert isinstance(chosen, TelnyxSTT)
    assert (chosen.name, chosen.data_flow.provider) == ("telnyx", "Telnyx")
    assert KEY not in repr(chosen) and "humain/realtime" in repr(chosen)
    asyncio.run(chosen.aclose())
