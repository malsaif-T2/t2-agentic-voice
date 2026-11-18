"""Scribe v3 Live behind the streaming port (adapters/elevenlabs_live.py; plan 010's 5.1) against
a fake socket (nothing leaves the machine): the session's query and key, `session_started`
awaited, the audio in 20 ms messages and the commit after its last part, each commit answered in
order and an answer with no commit waiting dropped, a keepalive, and each failure (an error
message, a lost socket, a refused handshake, no `session_started`, a backlog, a close) a
ProviderError that fails every commit waiting and shows no key or words."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters import elevenlabs_live
from t2_agentic_voice.adapters.elevenlabs_live import LiveStream
from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
from t2_agentic_voice.adapters.provider_socket import Opener
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.transcript_stream import StreamingSpeechToText

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.live_support import STARTED, FakeScribe, refused, said
from tests.t2_agentic_voice.adapters.provider_support import (
    HEARD,
    KEY,
    closed,
    handshake_refused,
    refusing,
)
from tests.t2_agentic_voice.fakes import FakeSpeechToText

FRAME = 640  # 20 ms at 16 kHz


def _live(
    scribe: FakeScribe,
    body: Callable[[LiveStream], Awaitable[None]],
    *,
    language: str | None = "en",
    prompt: str | None = None,
) -> None:
    async def go() -> None:
        stt = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0, opener=scribe.opener)
        stream = await stt.open_stream(language=language, prompt=prompt, sample_rate=16_000)
        try:
            await body(stream)
        finally:
            await stream.aclose()
            await stt.aclose()

    asyncio.run(go())


async def _until(check: Callable[[], bool]) -> None:
    async with asyncio.timeout(5):
        while not check():
            await asyncio.sleep(0.005)


def test_the_stream_opens_on_the_realtime_endpoint_with_the_key_and_its_query() -> None:
    scribe = FakeScribe()
    long_term = "a keyterm far past twenty characters"
    prompt = ", ".join(["Ole5", "OTP", long_term, "كلمة المرور", *(f"t{n}" for n in range(60))])

    async def body(stream: LiveStream) -> None:
        assert stream.failure is None

    _live(scribe, body, language="ar", prompt=prompt)
    ((url, headers, timeout_s),) = scribe.opened
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "wss",
        "api.elevenlabs.io",
        "/v1/speech-to-text/realtime",
    )
    query = parse_qs(parts.query)
    assert {name: values for name, values in query.items() if name != "keyterms"} == {
        "model_id": ["scribe_v3_live"],
        "audio_format": ["pcm_16000"],
        "commit_strategy": ["manual"],
        "language_code": ["ar"],
        "include_language_detection": ["true"],
    }
    terms = query["keyterms"]
    assert terms[:3] == ["Ole5", "OTP", "كلمة المرور"] and len(terms) == 50  # realtime's cap
    assert long_term not in terms and all(len(term) <= 20 for term in terms)
    assert headers == {"xi-api-key": KEY} and timeout_s == elevenlabs_live.OPEN_S
    assert scribe.closes == 1 and KEY not in url


def test_audio_goes_in_20_ms_messages_and_a_commit_after_its_last_part() -> None:
    scribe = FakeScribe(["hello there"])
    audio = bytes(range(256)) * 3  # 768 bytes: one whole frame, then 128 bytes

    async def body(stream: LiveStream) -> None:
        stream.feed(audio)
        number = stream.commit()
        heard = await stream.committed(number)
        assert (number, heard.text, heard.language) == (0, "hello there", "en")

    _live(scribe, body)
    first, rest, commit = scribe.messages()
    assert first == {
        "message_type": "input_audio_chunk",
        "audio_base_64": base64.b64encode(audio[:FRAME]).decode(),
        "commit": False,
        "sample_rate": 16_000,
    }
    assert base64.b64decode(str(rest["audio_base_64"])) == audio[FRAME:] and not rest["commit"]
    assert (commit["audio_base_64"], commit["commit"]) == ("", True)
    assert scribe.audio() == audio


def test_commits_are_answered_in_order_and_an_answer_with_no_commit_waiting_is_dropped() -> None:
    partial = json.dumps({"message_type": "partial_transcript", "text": "hel"})
    early = (STARTED, partial, said("too soon"))
    scribe = FakeScribe(["first words", "second words"], started=early)

    async def body(stream: LiveStream) -> None:
        await asyncio.sleep(0.02)  # the early answer read, with no commit waiting
        stream.feed(bytes(FRAME))
        first = stream.commit()
        stream.feed(bytes(FRAME))
        second = stream.commit()
        assert (await stream.committed(second)).text == "second words"
        assert (await stream.committed(first)).text == "first words"
        assert (await stream.committed(first)).text == "first words"  # read again
        assert stream.dropped == 1 and stream.failure is None

    _live(scribe, body)


def test_a_cancelled_wait_leaves_the_answer_to_another() -> None:
    scribe = FakeScribe(["kept words"], delay_s=0.1)

    async def body(stream: LiveStream) -> None:
        number = stream.commit()
        waiting = asyncio.create_task(stream.committed(number))
        await asyncio.sleep(0.02)
        waiting.cancel()
        assert (await stream.committed(number)).text == "kept words"

    _live(scribe, body)


@pytest.mark.parametrize(
    ("answer", "kind", "reason"),
    [
        (refused("commit_throttled", HEARD), "rate_limited", "commit_throttled"),
        (refused("auth_error", HEARD), "rejected", "auth_error"),
        (refused("something_new_error", HEARD), "server_error", "error"),
        (closed(1011), "connection_lost", "ConnectionClosedError"),
        ('{"text": "no type"}', "server_error", "unreadable_message"),
    ],
    ids=["throttled", "auth", "unknown error", "lost", "unreadable"],
)
def test_a_failure_fails_every_commit_waiting_and_shows_no_key_or_words(
    answer: str | Exception, kind: str, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    scribe = FakeScribe([answer])
    errors: list[ProviderError] = []

    async def body(stream: LiveStream) -> None:
        stream.feed(bytes(FRAME))
        number = stream.commit()
        with pytest.raises(ProviderError) as raised:
            await stream.committed(number)
        errors.append(raised.value)
        assert stream.failure is not None and stream.failure.kind == kind
        await _until(lambda: scribe.closes == 1)
        sent = len(scribe.sent)
        stream.feed(bytes(FRAME))  # dropped
        with pytest.raises(ProviderError):
            await stream.committed(stream.commit())  # fails at once
        assert len(scribe.sent) == sent

    _live(scribe, body)
    (error,) = errors
    assert (error.kind, error.details["provider"], error.details["error"]) == (
        kind,
        "elevenlabs",
        reason,
    )
    assert holding(KEY, shown(error, caplog=caplog)) == []
    assert holding(HEARD, shown(error, caplog=caplog)) == []


@pytest.mark.parametrize(
    ("started", "opener_error", "kind"),
    [
        ((), handshake_refused(401), "rejected"),
        ((refused("auth_error", HEARD),), None, "rejected"),
        ((refused("quota_exceeded", HEARD),), None, "rejected"),
        ((), None, "timeout"),
    ],
    ids=["refused handshake", "auth error", "quota", "no session_started"],
)
def test_a_session_that_does_not_start_is_a_provider_error(
    started: tuple[str, ...],
    opener_error: Exception | None,
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(elevenlabs_live, "OPEN_S", 0.1)
    scribe = FakeScribe(started=started)
    opener = scribe.opener if opener_error is None else cast(Opener, refusing(opener_error))

    async def go() -> ProviderError:
        stt = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0, opener=opener)
        with pytest.raises(ProviderError) as raised:
            await stt.open_stream(language="en", prompt=None, sample_rate=16_000)
        await stt.aclose()
        return raised.value

    error = asyncio.run(go())
    assert error.kind == kind and holding(HEARD, shown(error)) == []
    assert scribe.closes == (0 if opener_error is not None else 1)


def test_a_sample_rate_realtime_does_not_take_is_refused_before_any_socket() -> None:
    scribe = FakeScribe()

    async def go() -> None:
        stt = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0, opener=scribe.opener)
        with pytest.raises(ProviderError) as raised:
            await stt.open_stream(language="en", prompt=None, sample_rate=11_025)
        assert raised.value.kind == "rejected"
        await stt.aclose()

    asyncio.run(go())
    assert scribe.opened == []


def test_with_nothing_fed_a_message_of_silence_keeps_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(elevenlabs_live, "KEEPALIVE_S", 0.02)
    scribe = FakeScribe()

    async def body(stream: LiveStream) -> None:
        await _until(lambda: len(scribe.sent) >= 2)

    _live(scribe, body)
    assert scribe.audio()[: 2 * FRAME] == bytes(2 * FRAME) and scribe.commits() == 0


def test_audio_that_cannot_be_sent_in_time_fails_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(elevenlabs_live, "MOST_QUEUED_S", 0.03)
    scribe = FakeScribe()

    async def body(stream: LiveStream) -> None:
        stream.feed(bytes(3 * FRAME))  # queued at once, before the sender runs
        assert stream.failure is not None and stream.failure.kind == "timeout"
        assert stream.failure.details["error"] == "send_backlog"

    _live(scribe, body)


def test_closing_fails_a_commit_still_waiting_and_closes_the_socket() -> None:
    scribe = FakeScribe([None])

    async def body(stream: LiveStream) -> None:
        number = stream.commit()
        waiting = asyncio.create_task(stream.committed(number))
        await asyncio.sleep(0.02)
        await stream.aclose()
        with pytest.raises(ProviderError) as raised:
            await waiting
        assert raised.value.kind == "connection_lost"

    _live(scribe, body)
    assert scribe.closes == 1


def test_the_adapter_streams_and_a_batch_only_provider_does_not() -> None:
    stt = ElevenLabsSTT(api_key=SecretStr(KEY), timeout_s=2.0)
    assert isinstance(stt, StreamingSpeechToText)
    assert not isinstance(FakeSpeechToText(), StreamingSpeechToText)
    asyncio.run(stt.aclose())
