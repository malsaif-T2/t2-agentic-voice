"""TelnyxTTS against a fake Telnyx WebSocket and a fake HTTP transport (nothing leaves the
machine): the handshake's URL and key, the three messages a take sends, its base64 frames read
as 16 kHz PCM in whole samples until `isFinal` or an orderly close, an error frame as a
retryable server error, each failure showing no key or text, a cancel, the language check
against Telnyx's voices list, and the composition root's choice of it by `tts.provider`
(D-114)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import cast

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.provider_socket import Opener
from t2_agentic_voice.adapters.telnyx_tts import TelnyxTTS
from t2_agentic_voice.api.providers import tts_kinds
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.provider_support import (
    KEY,
    FakeProvider,
    FakeSocket,
    Message,
    Reply,
    closed,
    handshake_refused,
    refusing,
    sent_json,
)
from tests.t2_agentic_voice.adapters.tts_support import silence, tone

TEXT = "هذه كلمات مختلقة للاختبار ٤٤٧١ تقال بصوت سعد."
VOICES: dict[LanguageTag, TtsVoice] = {"ar-SA": TtsVoice(model="Telnyx.Bayan", voice="Fahd")}
SPEECH = silence(0.1, 16_000) + tone(3.0, 16_000)


def frames(pcm: bytes, pieces: int = 4) -> list[Reply]:
    """Telnyx's frames for `pcm`, split anywhere, then the text's echo and the final frame."""
    size = len(pcm) // pieces + 1
    audio: list[Reply] = [
        json.dumps({"audio": base64.b64encode(pcm[at : at + size]).decode(), "isFinal": False})
        for at in range(0, len(pcm), size)
    ]
    return [*audio, json.dumps({"audio": None, "text": TEXT}), json.dumps({"isFinal": True})]


def answering(replies: list[Reply]) -> FakeSocket:
    """A socket that answers the take's closing message with `replies`."""
    return FakeSocket(lambda message: replies if json.loads(message) == {"text": ""} else [])


def _tts(opener: object, *, timeout_s: float = 6.0) -> TelnyxTTS:
    """The adapter over `opener` (a fake socket's, or one whose handshake fails)."""
    return TelnyxTTS(
        api_key=SecretStr(KEY), languages=VOICES, timeout_s=timeout_s, opener=cast(Opener, opener)
    )


def _take(tts: TelnyxTTS, text: str = TEXT) -> list[AudioChunk]:
    async def go() -> list[AudioChunk]:
        try:
            return [chunk async for chunk in tts.synthesize(text, language="ar-SA")]
        finally:
            await tts.aclose()

    return asyncio.run(go())


def test_a_take_opens_the_voices_socket_and_sends_its_three_messages() -> None:
    socket = answering(frames(SPEECH))
    _take(_tts(socket.opener))
    ((url, headers, timeout),) = socket.opened
    assert url == (
        "wss://api.telnyx.com/v2/text-to-speech/speech?voice=Telnyx.Bayan.Fahd"
        "&audio_format=linear16&sample_rate=16000"
    )
    assert (headers, timeout) == ({"Authorization": f"Bearer {KEY}"}, 6.0)
    assert sent_json(socket) == [{"text": " "}, {"text": TEXT}, {"text": ""}]
    assert socket.closes == 1


def test_the_frames_audio_comes_in_whole_samples_at_16_khz() -> None:
    chunks = _take(_tts(answering(frames(SPEECH, pieces=7)).opener))
    assert b"".join(chunk.pcm16 for chunk in chunks) == SPEECH
    assert all(len(chunk.pcm16) % 2 == 0 and chunk.sample_rate == 16_000 for chunk in chunks)
    assert not any(chunk.cut_short for chunk in chunks) and len(chunks) > 1


def test_an_orderly_close_ends_the_take_as_its_final_frame_does() -> None:
    replies = [*frames(SPEECH)[:-1], closed(1000)]
    assert b"".join(c.pcm16 for c in _take(_tts(answering(replies).opener))) == SPEECH


def test_a_take_with_no_audio_ends_with_one_empty_chunk_flagged_cut_short() -> None:
    (chunk,) = _take(_tts(answering([json.dumps({"isFinal": True})]).opener))
    assert (chunk.pcm16, chunk.cut_short, chunk.sample_rate) == (b"", True, 16_000)


FAILURES: list[tuple[str, list[Reply] | Exception, str, bool]] = [
    ("error frame", [json.dumps({"error": {"detail": TEXT, "key": KEY}})], "server_error", True),
    ("not json", [f"{{{TEXT}"], "server_error", False),
    ("bad audio", [json.dumps({"audio": f"%%{TEXT}"})], "server_error", False),
    ("lost", [closed(1011)], "connection_lost", True),
    ("refused close", [closed(1008)], "rejected", False),
    ("handshake 401", handshake_refused(401), "rejected", False),
    ("handshake 429", handshake_refused(429, "3"), "rate_limited", True),
    ("no network", OSError(f"{KEY} {TEXT}"), "connection_lost", True),
]


@pytest.mark.parametrize(("name", "answer", "kind", "retryable"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_or_text(
    name: str,
    answer: list[Reply] | Exception,
    kind: str,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider and the failure's class, nothing it was sent."""
    caplog.set_level(logging.DEBUG)
    opener = refusing(answer) if isinstance(answer, Exception) else answering(answer).opener
    tts = _tts(opener)
    with pytest.raises(ProviderError) as raised:
        _take(tts)
    error = raised.value
    assert (error.kind, error.retryable, error.details["provider"]) == (kind, retryable, "telnyx")
    assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, TEXT):
        assert holding(value, surfaces) == []


def test_a_wait_for_a_frame_past_its_timeout_is_a_timeout() -> None:
    with pytest.raises(ProviderError) as raised:
        _take(_tts(FakeSocket(lambda message: []).opener, timeout_s=0.05))
    assert (raised.value.kind, raised.value.retryable) == ("timeout", True)


def test_a_cancel_stops_the_take_at_once_and_closes_its_socket() -> None:
    def first_only(message: Message) -> list[Reply]:
        return frames(SPEECH)[:1] if json.loads(message) == {"text": ""} else []

    socket = FakeSocket(first_only)

    async def go() -> None:
        tts = _tts(socket.opener)
        played = asyncio.Event()

        async def play() -> None:
            async for _ in tts.synthesize(TEXT, language="ar-SA"):
                played.set()

        task = asyncio.create_task(play())
        await played.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await tts.aclose()

    asyncio.run(asyncio.wait_for(go(), 5))
    assert socket.closes == 1


def test_a_language_with_no_voice_is_refused_unopened() -> None:
    socket = answering(frames(SPEECH))
    tts = _tts(socket.opener)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(_drain(tts, "en"))
    assert raised.value.details == {"error": "no_voice"} and socket.opened == []
    assert tts.max_chars("ar-SA") is None


async def _drain(tts: TelnyxTTS, language: str) -> None:
    try:
        async for _ in tts.synthesize(TEXT, language=language):
            pass
    finally:
        await tts.aclose()


def test_the_language_check_reads_the_voices_of_the_voices_provider() -> None:
    listing = {"voices": [{"id": "Telnyx.Bayan.Jasem"}, {"id": "Telnyx.Bayan.Fahd", "x": 1}]}
    date = {"date": "Tue, 17 Nov 2026 10:36:05 GMT"}
    fake = FakeProvider(lambda request: httpx.Response(200, json=listing, headers=date))

    async def check(voices: dict[LanguageTag, TtsVoice], language: str = "ar-SA") -> object:
        tts = TelnyxTTS(
            api_key=SecretStr(KEY), languages=voices, timeout_s=6.0, transport=fake.transport()
        )
        try:
            return await tts.check_language(language)
        finally:
            await tts.aclose()

    assert str(asyncio.run(check(VOICES))) == "2026-11-17 10:36:05+00:00"
    (request,) = fake.requests
    assert str(request.url) == "https://api.telnyx.com/v2/text-to-speech/voices?provider=telnyx"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    other: dict[LanguageTag, TtsVoice] = {"ar-SA": TtsVoice(model="Telnyx.Bayan", voice="Tamer")}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(check(other))
    assert raised.value.details == {"error": "voice_not_listed", "model": "Telnyx.Bayan"}
    with pytest.raises(ConfigurationError):
        asyncio.run(check(VOICES, "en"))


def test_tts_provider_picks_it_with_bayan_voices_and_needs_its_key() -> None:
    settings = VoiceSettings.model_validate(
        {"env": "test", "tts": {"provider": "telnyx"}, "telnyx": {"api_key": KEY}}
    )
    assert isinstance(tts_kinds()[settings.tts.provider](settings), TelnyxTTS)
    voices = {tag: f"{v.model}.{v.voice}" for tag, v in settings.tts.languages.items()}
    assert voices == {
        "ar-SA": "Telnyx.Bayan.Fahd",
        "ar": "Telnyx.Bayan.Fahd",
        "en": "Telnyx.Bayan.Michael",
    }
    bare = VoiceSettings.model_validate({"env": "test", "tts": {"provider": "telnyx"}})
    with pytest.raises(ConfigurationError) as raised:
        TelnyxTTS.from_settings(bare)
    assert raised.value.details == {"setting": "T2V_TELNYX__API_KEY"}
