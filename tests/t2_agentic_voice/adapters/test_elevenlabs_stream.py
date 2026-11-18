"""ElevenLabs' Text-to-Dialogue session (adapters/elevenlabs_stream.py, D-121) against fake
sockets (nothing leaves the machine): the socket opened for the call's language with the voice
registered, each clause flushed and its audio read in order until its turn's end, a reply's
first clause a new turn, a cut that lets the socket go and opens the next in the background,
keep-alive on an idle socket only, a change of language, each failure a ProviderError showing no
key or text that breaks the session, its close, and which models stream (the clause cache passes
it on)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.clause_cache import ClauseCache
from t2_agentic_voice.adapters.elevenlabs_stream import DIALOGUE_URL, DialogueStream
from t2_agentic_voice.adapters.elevenlabs_tts import ElevenLabsTTS
from t2_agentic_voice.adapters.provider_socket import Opener
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.tts import LanguageTag, TtsVoice
from t2_agentic_voice.domain.ports.speech_stream import StreamingTextToSpeech
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.provider_support import (
    KEY,
    FakeSocket,
    Message,
    Reply,
    closed,
    handshake_refused,
    refusing,
    sent_json,
)
from tests.t2_agentic_voice.adapters.tts_support import tone
from tests.t2_agentic_voice.fakes import FakeTextToSpeech

TEXT = "هذه كلمات مختلقة للاختبار ٤٤٧١ تقال بصوت سعد،"
VOICE = "MadeUpVoice0123456789"
TURBO = TtsVoice(model="eleven_v4_turbo", voice=VOICE)
VOICES: dict[LanguageTag, TtsVoice] = {"ar-SA": TURBO, "ar": TURBO, "en": TURBO}
SPEECH = tone(3.0)  # long enough for TEXT: not cut short
END = json.dumps({"audio": None, "is_final_audio_for_turn": True})


def frames(pcm: bytes, pieces: int = 4, *, end: bool = True) -> list[Reply]:
    """ElevenLabs' audio frames for `pcm`, split anywhere (inside a sample too), then the end."""
    size = len(pcm) // pieces + 1
    audio: list[Reply] = [
        json.dumps({"audio": base64.b64encode(pcm[at : at + size]).decode(), "alignment": None})
        for at in range(0, len(pcm), size)
    ]
    return [*audio, END] if end else audio


def speaking(replies: list[Reply]) -> Callable[[Message], list[Reply]]:
    """A provider that answers each clause with `replies`, and nothing else."""
    return lambda message: replies if "inputs" in json.loads(message) else []


class Sockets:
    """An opener handing a new fake socket to each open, each answering as `answer` gives."""

    def __init__(self, answer: Callable[[Message], list[Reply]]) -> None:
        self.answer = answer
        self.made: list[FakeSocket] = []

    async def opener(self, url: str, headers: Mapping[str, str], timeout_s: float) -> FakeSocket:
        socket = FakeSocket(self.answer)
        socket.opened.append((url, dict(headers), timeout_s))
        self.made.append(socket)
        return socket


def _stream(opener: object, *, language: str = "ar-SA", **options: float) -> DialogueStream:
    return DialogueStream(
        api_key=SecretStr(KEY),
        voices=VOICES,
        language=language,
        timeout_s=options.get("timeout_s", 6.0),
        opener=cast(Opener, opener),
        keep_alive_s=options.get("keep_alive_s", 60.0),
    )


async def _said(stream: DialogueStream, text: str = TEXT, **options: object) -> list[AudioChunk]:
    language = cast(str, options.get("language", "ar-SA"))
    new_turn = bool(options.get("new_turn", False))
    return [chunk async for chunk in stream.say(text, language=language, new_turn=new_turn)]


def _run(body: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(asyncio.wait_for(body(), 5))


def _inputs(socket: FakeSocket) -> list[dict[str, object]]:
    return [message for message in sent_json(socket) if "inputs" in message]


def test_the_session_opens_the_calls_socket_at_once_and_registers_its_voice() -> None:
    sockets = Sockets(speaking(frames(SPEECH)))

    async def body() -> None:
        stream = _stream(sockets.opener)
        await asyncio.sleep(0.05)  # opened in the background, before any clause
        assert len(sockets.made) == 1
        await stream.aclose()

    _run(body)
    ((url, headers, timeout),) = sockets.made[0].opened
    assert url == (
        f"{DIALOGUE_URL}?model_id=eleven_v4_turbo&output_format=pcm_24000&language_code=ar"
    )
    assert (headers, timeout) == ({"xi-api-key": KEY}, 6.0)
    assert sent_json(sockets.made[0]) == [{"voices": [VOICE]}]
    assert sockets.made[0].closes == 1


def test_each_clause_is_flushed_and_its_audio_comes_whole_and_in_order() -> None:
    sockets = Sockets(speaking(frames(SPEECH, pieces=7)))
    taken: list[list[AudioChunk]] = []

    async def body() -> None:
        stream = _stream(sockets.opener)
        taken.append(await _said(stream, new_turn=True))  # the socket's first: no new turn
        taken.append(await _said(stream, "and then, "))
        taken.append(await _said(stream, "A new reply.", new_turn=True))
        await stream.aclose()

    _run(body)
    for chunks in taken:
        assert b"".join(chunk.pcm16 for chunk in chunks) == SPEECH
        assert all(len(c.pcm16) % 2 == 0 and c.sample_rate == 24_000 for c in chunks)
        assert not any(chunk.cut_short for chunk in chunks)
    (socket,) = sockets.made
    assert _inputs(socket) == [
        {"inputs": [{"text": f"{TEXT} ", "voice_id": VOICE}], "flush": True},
        {"inputs": [{"text": "and then, ", "voice_id": VOICE}], "flush": True},
        {"inputs": [{"text": "A new reply. ", "voice_id": VOICE, "new_turn": True}], "flush": True},
    ]


def test_a_cut_lets_the_socket_go_and_the_next_clause_finds_a_new_one_open() -> None:
    """The first socket sends part of a clause and never its end: the stop's `cut`, then the
    bridge closing the clause, drop it; a new socket opens at once, and the next clause plays
    on it."""
    first = True

    def answer(message: Message) -> list[Reply]:
        nonlocal first
        if "inputs" not in json.loads(message):
            return []
        if first:
            first = False
            return frames(SPEECH, end=False)[:1]
        return frames(SPEECH)

    sockets = Sockets(answer)
    after: list[AudioChunk] = []

    async def body() -> None:
        stream = _stream(sockets.opener)
        said = stream.say(TEXT, language="ar-SA", new_turn=True)
        await anext(said)
        stream.cut()
        await said.aclose()
        await asyncio.sleep(0.05)
        assert len(sockets.made) == 2 and sockets.made[0].closes == 1
        after.extend(await _said(stream, "Again.", new_turn=True))
        await stream.aclose()

    _run(body)
    assert b"".join(chunk.pcm16 for chunk in after) == SPEECH
    old, new = sockets.made
    assert len(_inputs(old)) == 1
    assert sent_json(new)[0] == {"voices": [VOICE]}
    assert _inputs(new) == [{"inputs": [{"text": "Again. ", "voice_id": VOICE}], "flush": True}]


@pytest.mark.parametrize("how", ["closed", "cancelled"])
def test_a_clause_closed_or_cancelled_before_its_end_is_a_cut(how: str) -> None:
    sockets = Sockets(speaking(frames(SPEECH, end=False)[:1]))

    async def body() -> None:
        stream = _stream(sockets.opener)
        said = stream.say(TEXT, language="ar-SA", new_turn=False)
        if how == "closed":
            await anext(said)
            await said.aclose()
        else:
            task = asyncio.create_task(_drain(said))
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0.05)
        assert len(sockets.made) == 2 and sockets.made[0].closes == 1
        await stream.aclose()
        assert sockets.made[1].closes == 1

    _run(body)


async def _drain(chunks: AsyncIterator[AudioChunk]) -> None:
    async for _ in chunks:
        pass


def test_keep_alive_goes_on_an_idle_socket_and_never_during_a_clause() -> None:
    def answer(message: Message) -> list[Reply]:
        return frames(SPEECH, end=False) if "inputs" in json.loads(message) else []

    sockets = Sockets(answer)
    marks: dict[str, int] = {}

    async def body() -> None:
        stream = _stream(sockets.opener, keep_alive_s=0.04)
        await asyncio.sleep(0.2)
        socket = sockets.made[0]
        marks["idle"] = sent_json(socket).count({"keep_alive": True})
        said = stream.say(TEXT, language="ar-SA", new_turn=False)
        await anext(said)
        before = len(socket.sent)
        await asyncio.sleep(0.2)  # the clause's end has not come: no keep-alive meanwhile
        marks["during"] = len(socket.sent) - before
        socket._replies.put_nowait(END)  # the provider ends the clause now
        await _drain(said)
        await asyncio.sleep(0.2)
        marks["after"] = sent_json(socket).count({"keep_alive": True}) - marks["idle"]
        await stream.aclose()

    _run(body)
    assert marks["idle"] >= 2 and marks["during"] == 0 and marks["after"] >= 2


FAILURES: list[tuple[str, list[Reply] | Exception, str, bool]] = [
    (
        "busy",
        [json.dumps({"message": f"{TEXT} {KEY}", "error": "too_many_concurrent_requests"})],
        "rate_limited",
        True,
    ),
    (
        "spent",
        [json.dumps({"message": TEXT, "error": "quota_exceeded", "code": 1008})],
        "rejected",
        False,
    ),
    ("odd error", [json.dumps({"message": TEXT, "error": f"{KEY} {TEXT}"})], "server_error", False),
    ("not json", [f"{{{TEXT}"], "server_error", False),
    ("bad audio", [json.dumps({"audio": f"%%{TEXT}"})], "server_error", False),
    ("lost", [closed(1011)], "connection_lost", True),
    ("refused close", [closed(1008)], "rejected", False),
    ("handshake 401", handshake_refused(401), "rejected", False),
    ("handshake 429", handshake_refused(429, "3"), "rate_limited", True),
    ("no network", OSError(f"{KEY} {TEXT}"), "connection_lost", True),
]


@pytest.mark.parametrize(("name", "answer", "kind", "retryable"), FAILURES)
def test_each_failure_is_a_provider_error_showing_no_key_or_text_and_breaks_the_session(
    name: str,
    answer: list[Reply] | Exception,
    kind: str,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """GP-19: the error holds the provider and the failure's name, nothing it was sent; every
    later clause raises it, with no new socket."""
    caplog.set_level(logging.DEBUG)
    sockets = Sockets(speaking(answer) if isinstance(answer, list) else lambda message: [])
    opener = refusing(answer) if isinstance(answer, Exception) else sockets.opener
    raised: list[ProviderError] = []

    async def body() -> None:
        stream = _stream(opener)
        for _ in range(2):
            with pytest.raises(ProviderError) as error:
                await _said(stream)
            raised.append(error.value)
        await stream.aclose()

    _run(body)
    error, again = raised
    assert error is again and len(sockets.made) <= 1
    assert (error.kind, error.retryable, error.details["provider"]) == (
        kind,
        retryable,
        "elevenlabs",
    )
    assert (error.__cause__, error.__context__) == (None, None)
    surfaces = shown(error, caplog=caplog, capsys=capsys)
    for value in (KEY, TEXT):
        assert holding(value, surfaces) == []


def test_a_wait_for_a_frame_past_its_timeout_is_a_timeout() -> None:
    sockets = Sockets(lambda message: [])

    async def body() -> None:
        stream = _stream(sockets.opener, timeout_s=0.05)
        with pytest.raises(ProviderError) as raised:
            await _said(stream)
        assert (raised.value.kind, raised.value.retryable) == ("timeout", True)
        await stream.aclose()

    _run(body)


def test_a_clause_in_another_language_opens_that_languages_socket() -> None:
    sockets = Sockets(speaking(frames(SPEECH)))

    async def body() -> None:
        stream = _stream(sockets.opener)
        await _said(stream)
        await _said(stream, "Arabic, MSA.", language="ar")  # the same socket: code `ar`
        await _said(stream, "In English.", language="en")
        await asyncio.sleep(0.05)
        await stream.aclose()

    _run(body)
    arabic, english = sockets.made
    assert arabic.opened[0][0].endswith("language_code=ar") and len(_inputs(arabic)) == 2
    assert english.opened[0][0].endswith("language_code=en") and len(_inputs(english)) == 1
    assert (arabic.closes, english.closes) == (1, 1)


def test_the_close_leaves_no_task_and_a_language_with_no_voice_is_refused_unsent() -> None:
    sockets = Sockets(speaking(frames(SPEECH)))
    left: list[asyncio.Task[object]] = []

    async def body() -> None:
        stream = _stream(sockets.opener)
        with pytest.raises(ProviderError) as raised:
            await _said(stream, language="fr")
        assert raised.value.details == {"error": "no_voice"}
        await _said(stream)
        await stream.aclose()
        await stream.aclose()
        left.extend(t for t in asyncio.all_tasks() if t is not asyncio.current_task())

    _run(body)
    assert left == [] and sockets.made[0].closes == 1


def test_which_languages_stream_and_the_clause_cache_passes_it_on(tmp_path: Path) -> None:
    flash = TtsVoice(model="eleven_flash_v2_5", voice=VOICE)
    tts = ElevenLabsTTS(
        api_key=SecretStr(KEY), languages={"ar-SA": TURBO, "en": flash}, timeout_s=6
    )
    assert isinstance(tts, StreamingTextToSpeech)
    assert (tts.streams("ar-SA"), tts.streams("en"), tts.streams("ar")) == (True, False, False)

    def cache(over: object) -> ClauseCache:
        return ClauseCache(
            cast(ElevenLabsTTS, over), folder=tmp_path, voices=VOICES, trim_silence=False, max_mb=1
        )

    assert cache(tts).streams("ar-SA") and not cache(tts).streams("en")
    plain = cache(FakeTextToSpeech())
    assert not plain.streams("ar-SA")
    with pytest.raises(TypeError):
        plain.open_stream(language="ar-SA")
    sockets = Sockets(speaking(frames(SPEECH)))
    opened = ElevenLabsTTS(
        api_key=SecretStr(KEY), languages=VOICES, timeout_s=6, opener=cast(Opener, sockets.opener)
    )

    async def body() -> None:
        stream = cache(opened).open_stream(language="en")
        assert isinstance(stream, DialogueStream)
        await _said(stream, "Hello.", language="en")
        await stream.aclose()
        await opened.aclose()

    _run(body)
    assert sockets.made[0].opened[0][0].endswith("language_code=en")
