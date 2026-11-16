"""NabrahSTT against a fake Nabrah WebSocket (nothing leaves the machine): the config message
with the key and the priority words, the ready message awaited, the audio at 16 kHz and the eof,
the finals read; each failure as a ProviderError showing no key, audio or transcript, a timeout
and a cancel, and the composition root's choice of it by `stt.provider` (D-100)."""

from __future__ import annotations

import asyncio
import json
import logging
import struct

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.nabrah_stt import NabrahSTT, at_16k
from t2_agentic_voice.api.providers import Providers
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.provider_support import (
    CLIP,
    HEARD,
    KEY,
    FakeSocket,
    Message,
    Reply,
    closed,
    keyed,
    refusing,
    sent_audio,
    sent_json,
)

EOF_MESSAGE = json.dumps({"type": "eof"})
READY = json.dumps({"type": "ready"})


def _said(text: str, *, final: bool = True, segment: str | None = None) -> str:
    frame: dict[str, object] = {"type": "transcript", "text": text, "is_final": final}
    if segment is not None:
        frame["segment_text"] = segment
    return json.dumps(frame, ensure_ascii=False)


def _nabrah(*replies: Reply, ready: list[Reply] | None = None) -> FakeSocket:
    """A Nabrah that answers the config with `ready` (its ready message by default) and the
    eof with `replies`."""

    def answer(message: Message) -> list[Reply]:
        if message == EOF_MESSAGE:
            return list(replies)
        if isinstance(message, str) and "api_key" in message:
            return [READY] if ready is None else ready
        return []

    return FakeSocket(answer)


def _settings(**nabrah: object) -> VoiceSettings:
    return VoiceSettings.model_validate(
        {"env": "test", "nabrah": {"api_key": KEY, "quiet_s": 0.05, **nabrah}}
    )


def _run(
    socket: FakeSocket, *, prompt: str | None = None, clip: AudioClip = CLIP, **nabrah: object
) -> Transcript:
    async def go() -> Transcript:
        stt = NabrahSTT.from_settings(_settings(**nabrah), opener=socket.opener)
        try:
            return await stt.transcribe(clip, language="ar", prompt=prompt)
        finally:
            await stt.aclose()

    return asyncio.run(go())


def test_the_turn_sends_the_config_waits_for_ready_then_the_audio_and_the_eof() -> None:
    socket = _nabrah(
        _said("partial", final=False),
        _said(f"{HEARD} more", segment=f"{HEARD}<eot>"),
        _said("كلمة المرور"),
        closed(),
    )
    heard = _run(socket, prompt="Ole5, OTP , كلمة المرور,, Ole5")
    ((url, headers, timeout_s),) = socket.opened
    assert (url, headers, timeout_s) == ("wss://api.nabrah.ai/api/ext/stt/ws", {}, 10.0)
    config, eof = sent_json(socket)
    assert config == {
        "api_key": KEY,
        "priority_words": ["Ole5", "OTP", "كلمة المرور"],
        "priority_words_strength": 0.5,
    }
    assert eof == {"type": "eof"} and socket.sent[-1] == EOF_MESSAGE
    assert sent_audio(socket) == CLIP.pcm16
    assert {len(m) for m in socket.sent[1:-2] if isinstance(m, bytes)} == {5120}
    assert (heard.text, heard.language, heard.heard_language) == (
        f"{HEARD} كلمة المرور",
        "ar",
        None,
    )
    assert (heard.confidence, heard.billed_seconds, socket.closes) == (None, 1.0, 1)


def test_no_prompt_sends_no_priority_words_and_a_quiet_socket_ends_the_turn() -> None:
    socket = _nabrah(_said(HEARD))  # Nabrah never closes
    assert _run(socket).text == HEARD
    assert sent_json(socket)[0] == {"api_key": KEY}


def test_audio_at_another_rate_is_sent_at_16_khz() -> None:
    samples = [round(1000 * (i % 8)) for i in range(8000)]
    clip = AudioClip(pcm16=struct.pack(f"<{len(samples)}h", *samples), sample_rate=8000)
    sent = at_16k(clip)
    assert len(sent) == 2 * 16_000 and sent[:2] == clip.pcm16[:2]
    assert at_16k(CLIP) == CLIP.pcm16
    socket = _nabrah(closed())
    assert _run(socket, clip=clip).billed_seconds == 1.0 and sent_audio(socket) == sent


ERROR_FRAME = json.dumps({"type": "error", "message": f"{HEARD} {KEY}"})
FAILURES = [
    (refusing(OSError(f"{KEY} {HEARD}")), "connection_lost", True),
    (_nabrah(ready=[ERROR_FRAME]).opener, "server_error", False),
    (_nabrah(ready=[closed(1008)]).opener, "rejected", False),
    (_nabrah(ERROR_FRAME).opener, "server_error", False),
    (_nabrah(f"{{{HEARD}").opener, "server_error", False),
    (_nabrah(closed(1006)).opener, "connection_lost", True),
]


@pytest.mark.parametrize(("opener", "kind", "retryable"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_audio_or_transcript(
    opener: object,
    kind: str,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider, the failure's class or a close code, never the
    config message's key or a frame's text."""
    caplog.set_level(logging.DEBUG)

    async def go() -> None:
        stt = NabrahSTT.from_settings(_settings(), opener=opener)  # type: ignore[arg-type]
        await stt.transcribe(CLIP, language="ar", prompt="Ole5")

    with pytest.raises(ProviderError) as raised:
        asyncio.run(go())
    error = raised.value
    assert (error.kind, error.retryable, error.details["provider"]) == (kind, retryable, "nabrah")
    assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, HEARD, CLIP.pcm16[:64].hex()):
        assert holding(value, surfaces) == []


def test_a_turn_past_its_timeout_is_a_timeout_and_a_cancel_stops_it_at_once() -> None:
    hung = _nabrah(ready=[])  # never ready
    with pytest.raises(ProviderError) as raised:
        _run(hung, turn_timeout_s=0.05)
    assert (raised.value.kind, raised.value.retryable, hung.closes) == ("timeout", True, 1)

    async def cancelled() -> None:
        socket = _nabrah()  # never says anything after the eof
        stt = NabrahSTT.from_settings(_settings(quiet_s=10), opener=socket.opener)
        task = asyncio.create_task(stt.transcribe(CLIP, language=None, prompt=None))
        while not socket.sent or socket.sent[-1] != EOF_MESSAGE:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert socket.closes == 1

    asyncio.run(asyncio.wait_for(cancelled(), 5))


def test_with_no_key_nabrah_is_unavailable_and_says_which_setting_to_set() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "nabrah"}})
    for build in (NabrahSTT.from_settings, Providers.speech_to_text):
        with pytest.raises(ConfigurationError) as raised:
            build(settings)
        assert raised.value.details == {"setting": "T2V_NABRAH__API_KEY"}


@pytest.mark.parametrize("bad", ["  ", f"{KEY} x"])
def test_a_key_given_in_code_is_held_to_the_settings_rules(bad: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        NabrahSTT(api_key=SecretStr(bad))
    assert raised.value.details == {"setting": "T2V_NABRAH__API_KEY"}
    assert holding(KEY, shown(raised.value)) == []


def test_stt_provider_picks_nabrah() -> None:
    chosen = Providers.speech_to_text(keyed("nabrah", provider="nabrah"))
    assert isinstance(chosen, NabrahSTT)
    assert (chosen.name, chosen.data_flow.provider) == ("nabrah", "Nabrah")
    assert KEY not in repr(chosen)
    asyncio.run(chosen.aclose())
