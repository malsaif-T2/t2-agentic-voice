"""GroqTTS's checks (plan 003, Track B): the key in no repr, error or log line; `GROQ_*` variables
changing nothing in the request (the design's 7.3) and `GROQ_LOG` nothing on import (TD-003); a
cancel that stops within 50 ms and leaves no task or connection, and a Groq that stops answering
ended by `tts.timeout_s`, both over a real connection to a server on 127.0.0.1; the settings'
own checks on an adapter built in code (GP-20). Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast, get_args, get_type_hints

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_tts import GroqTTS
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk, TextToSpeech

from tests.isolation import dropped
from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import KEY, OTHER, SETTING, FakeGroq
from tests.t2_agentic_voice.adapters.tts_support import (
    ENGLISH,
    answer,
    speak,
    tone,
    tts_settings,
    wav,
)

VOICES = TtsSettings().languages
VALID: dict[str, Any] = {"api_key": SecretStr(KEY), "languages": VOICES}
VALID |= {"base_url": "https://api.groq.com", "timeout_s": 6.0}


@pytest.mark.parametrize("code", [400, 401, 429, 500])
def test_the_key_is_in_no_error_or_log_line_even_when_echoed(
    code: int, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    async def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"error": {"message": f"{dict(request.headers)}"}})

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(speak(FakeGroq(echo)))
    assert any(record.name.startswith("groq") for record in caplog.records)  # the SDK's debug
    assert holding(KEY, shown(raised.value, caplog=caplog, capsys=capsys)) == []


def test_a_text_to_speech_with_no_key_in_its_repr_and_no_groq_type_in_its_signatures() -> None:
    """The design's 5.3 (no public signature names a `groq` type) and 6.1 (the data flow)."""
    adapter = GroqTTS.from_settings(tts_settings())
    port: TextToSpeech = adapter  # mypy checks the port's shape
    assert [text for text in (repr(adapter), repr(vars(adapter))) if KEY in text] == []
    assert repr(adapter) == (
        "GroqTTS(languages={'ar-SA': 'canopylabs/orpheus-arabic-saudi:abdullah', "
        "'ar': 'canopylabs/orpheus-arabic-saudi:abdullah', "
        "'en': 'canopylabs/orpheus-v1-english:troy'}, base_url='https://api.groq.com', "
        "timeout_s=6.0, trim_silence=False)"
    )
    asyncio.run(adapter.aclose())
    assert (port.name, port.data_flow.provider) == ("groq", "Groq")

    def modules(hint: object) -> set[str]:  # of a type, and of every type inside it
        return {getattr(hint, "__module__", "")}.union(*(modules(a) for a in get_args(hint)))

    names = ("__init__", "from_settings", "max_chars", "synthesize", "check_language", "aclose")
    public = [getattr(GroqTTS, name) for name in names]
    named = set().union(*(modules(h) for f in public for h in get_type_hints(f).values()))
    assert "httpx" in named and not [name for name in named if name.split(".")[0] == "groq"]


MANY = f"AUTHORIZATION: Bearer {OTHER}\nx-made-up: 1\nHost: elsewhere.example\nContent-Length: 3"
MANY += "\nUser-Agent: made-up\nAccept: text/plain\nConnection: close\naccept-encoding: br"
SHELLS = [
    {"GROQ_API_KEY": OTHER, "GROQ_BASE_URL": "https://elsewhere.example"},
    {"GROQ_CUSTOM_HEADERS": f"authorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_CUSTOM_HEADERS": MANY + "\nX-Stainless-Lang: made-up"},
    {"GROQ_CUSTOM_HEADERS": "content-type: multipart/form-data"},  # beside the SDK's: still JSON
    {"GROQ_CUSTOM_HEADERS": "X-Stainless-Raw-Response: raw"},  # the SDK's marker
    # In another case, the SDK keeps both markers and reads the whole answer before it hands
    # any back: the same request and audio, its first chunk later (a debt row of plan 003).
    {"GROQ_CUSTOM_HEADERS": "x-stainless-raw-response: raw"},
]


def _take(chunks: list[AudioChunk]) -> tuple[bytes, set[int], tuple[object, ...]]:
    """A take as a call hears it: its audio, its rates, the first chunk's headroom and the last
    chunk's flag, however its chunks were cut."""
    first, last = chunks[0], chunks[-1]
    flags = (first.remaining_requests, first.remaining_tokens, last.cut_short)
    return b"".join(c.pcm16 for c in chunks), {c.sample_rate for c in chunks}, flags


@pytest.mark.parametrize("shell", SHELLS)
def test_the_sdks_own_variables_change_nothing(
    shell: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The request, header by header and byte by byte, and the take it gives (the plan's
    reading left whether the SDK's headers override `GROQ_CUSTOM_HEADERS` UNVERIFIED)."""
    headers = {"x-ratelimit-remaining-requests": "5", "x-ratelimit-remaining-tokens": "900"}
    plain = FakeGroq(answer(wav(tone(1.0)), headers=headers))
    shelled = FakeGroq(answer(wav(tone(1.0)), headers=headers))
    want = asyncio.run(speak(plain))
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "key.txt"
    path.write_text(f"{KEY}\n", encoding="utf-8")
    from_file = VoiceSettings(env="test", groq=GroqSettings(api_key_file=path))  # the same key

    async def again() -> list[AudioChunk]:
        adapter = GroqTTS.from_settings(from_file, transport=shelled)
        try:
            return [chunk async for chunk in adapter.synthesize(ENGLISH, language="en")]
        finally:
            await adapter.aclose()

    got = asyncio.run(again())
    (sent,), (asked,) = plain.requests, shelled.requests
    assert asked.headers.multi_items() == sent.headers.multi_items()
    assert (str(asked.url), asked.content) == (str(sent.url), sent.content)
    assert _take(got) == _take(want) == (tone(1.0), {24_000}, (5, 900, True))


@pytest.mark.parametrize(
    "line", ["Content-Type: multipart/form-data", "Content-Type: multipart/form-data; boundary=x"]
)
def test_a_content_type_line_that_makes_a_form_fails_the_request_unsent(
    line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", line)
    fake = FakeGroq()
    with pytest.raises(ProviderError) as raised:
        asyncio.run(speak(fake))
    error = raised.value
    assert (error.kind, error.retryable, error.details) == (
        "rejected",
        False,
        {"error": "foreign_body"},
    )
    assert fake.requests == []


_CHILD = """
import json, logging, sys
def state():
    levels = [logging.getLogger(name).level for name in ("groq", "httpx")]
    return [len(logging.getLogger().handlers), *levels]
before = state()
import {module}
print(json.dumps({{"imported": "groq" in sys.modules, "before": before, "after": state()}}))
"""
ADAPTER = "t2_agentic_voice.adapters.groq_tts"


def test_groq_log_changes_nothing_on_the_adapters_import() -> None:
    """In children whose shell sets `GROQ_LOG` alone of what the suite drops (tests/isolation.py),
    side by side, since importing groq takes seconds: `groq` alone reads it (the control), the
    adapter's import undoes it (TD-003)."""
    shell = {k: v for k, v in os.environ.items() if not dropped(k)}
    cases = [("groq", "debug"), (ADAPTER, "debug"), (ADAPTER, "info")]
    running = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD.format(module=module)],
            env=shell | {"GROQ_LOG": level},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for module, level in cases
    ]
    seen = []
    for child in running:
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0, err.decode("utf-8", errors="replace")
        seen.append(json.loads(out))
    control, *adapter = seen
    assert control["after"] == [control["before"][0] + 1, logging.DEBUG, logging.DEBUG]
    assert all(each["imported"] and each["after"] == each["before"] for each in adapter)


class Local(httpx.AsyncHTTPTransport):
    """Sends every request over a real connection to a server on 127.0.0.1, at `port`."""

    port, closed = 0, False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        return await super().handle_async_request(request)

    async def aclose(self) -> None:
        await super().aclose()
        self.closed = True


class Stalling:
    """A server on 127.0.0.1 that reads one request, sends `sent` (as much of an answer as it
    gives), then never sends more, until the client hangs up."""

    def __init__(self, sent: bytes) -> None:
        self.sent = sent
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(5)
        self.answered, self.hung_up = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        with contextlib.suppress(OSError), self.listener.accept()[0] as connection:
            connection.recv(65536)
            connection.sendall(self.sent)
            self.answered.set()
            while connection.recv(65536):
                pass
            self.hung_up.set()

    def __enter__(self) -> Local:
        self.thread.start()
        transport = Local()
        transport.port = self.listener.getsockname()[1]
        return transport

    def __exit__(self, *_: object) -> None:
        self.listener.close()
        self.thread.join(5)


def _streaming(body: bytes) -> bytes:
    """An HTTP answer's head and its first chunk of `body`, chunked, with no end."""
    head = b"HTTP/1.1 200 OK\r\ncontent-type: audio/wav\r\ntransfer-encoding: chunked\r\n\r\n"
    return head + f"{len(body):x}\r\n".encode() + body + b"\r\n"


async def _settle() -> set[asyncio.Task[Any]]:
    """The tasks still pending once the loop has settled, this one's aside: a take closed
    between chunks leaves httpx's own async generators suspended, and each one's finalizer, a
    task, closes the next on a later turn of the loop."""
    for _ in range(100):
        left = asyncio.all_tasks() - {asyncio.current_task()}
        if not left:
            break
        await asyncio.sleep(0)
    return left


@pytest.mark.parametrize("how", ["cancel", "close"])
def test_a_stopped_take_ends_at_once_and_closes_its_connection(how: str) -> None:
    """The design's 6.1: a take stopped mid-stream (its task cancelled while it waits for audio,
    or the take closed between chunks) ends in 50 ms, leaving no task and no connection."""
    server = Stalling(_streaming(wav(tone(0.1))))

    async def scenario(transport: Local) -> tuple[float, bytes, set[asyncio.Task[Any]]]:
        adapter = GroqTTS.from_settings(tts_settings(), transport=transport)
        take = cast("AsyncGenerator[AudioChunk, None]", adapter.synthesize(ENGLISH, language="en"))
        heard = b""
        while len(heard) < len(tone(0.1)):  # all the server sent, however the network cut it
            heard += (await anext(take)).pcm16

        async def next_chunk() -> AudioChunk:
            return await anext(take)

        if how == "cancel":
            waiting = asyncio.create_task(next_chunk())
            await asyncio.sleep(0.05)  # the next read is on the wire, its answer awaited
            start = time.perf_counter()
            waiting.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiting
        else:
            start = time.perf_counter()
            await take.aclose()
        took = time.perf_counter() - start
        left = await _settle()
        assert await asyncio.to_thread(server.hung_up.wait, 5)  # before aclose: the stop closed it
        await adapter.aclose()
        return took, heard, left

    with server as transport:
        took, heard, left = asyncio.run(scenario(transport))
    assert (heard, left, transport.closed) == (tone(0.1), set(), True)
    assert took < 0.05, f"the stop took {took * 1000:.1f} ms"


@pytest.mark.parametrize("answered", [b"", _streaming(wav(tone(0.1)))])
def test_a_groq_that_stops_answering_is_a_timeout_after_timeout_s(answered: bytes) -> None:
    """No answer at all, or an answer that stops mid-stream: each read waits `tts.timeout_s`,
    then the take fails as a retryable timeout and its connection is closed."""
    server = Stalling(answered)

    async def scenario(transport: Local) -> tuple[bytes, ProviderError | None, float]:
        adapter = GroqTTS.from_settings(tts_settings(timeout_s=0.3), transport=transport)
        heard, failed = b"", None
        start = time.perf_counter()
        try:
            async for chunk in adapter.synthesize(ENGLISH, language="en"):
                heard += chunk.pcm16
        except ProviderError as error:
            failed = error
        took = time.perf_counter() - start
        await adapter.aclose()
        return heard, failed, took

    with server as transport:
        heard, error, took = asyncio.run(scenario(transport))
        assert server.hung_up.wait(5)
    assert heard == (tone(0.1) if answered else b"")
    assert error is not None and (error.kind, error.retryable) == ("timeout", True)
    assert 0.3 <= took < 2.0


@pytest.mark.parametrize("file_text", [None, " \n"])
@pytest.mark.parametrize("key", [None, "   "])
def test_no_key_in_the_settings_is_a_configuration_error(
    key: str | None, file_text: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", OTHER)  # never read (the design's 7.3)
    (path := tmp_path / "key.txt").write_text(file_text or "", encoding="utf-8")
    groq: dict[str, Any] = {"api_key": None if key is None else SecretStr(key)}
    groq |= {"api_key_file": None if file_text is None else path}
    settings = VoiceSettings(env="test", groq=GroqSettings(**groq))
    with pytest.raises(ConfigurationError, match=SETTING) as raised:
        GroqTTS.from_settings(settings)
    assert raised.value.details == {"setting": SETTING}


def test_with_groq_api_key_set_instead_the_error_names_the_variable_to_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HELPDESK_VOICE_ENV", "test")
    monkeypatch.setenv("GROQ_API_KEY", OTHER)
    with pytest.raises(ConfigurationError) as raised:
        GroqTTS.from_settings(VoiceSettings.from_env(prefix="HELPDESK_VOICE_"))
    assert "GROQ_API_KEY is set, but the library never reads it" in raised.value.message
    assert raised.value.details == {"setting": "HELPDESK_VOICE_GROQ__API_KEY"}
    assert holding(OTHER, shown(raised.value)) == []


REFUSED = [
    ({"api_key": SecretStr("made up")}, SETTING),
    ({"base_url": "http://api.groq.com"}, "T2V_GROQ__BASE_URL"),
    ({"timeout_s": 0.0}, "T2V_TTS__TIMEOUT_S"),
    ({"languages": {"en": {"model": "made-up", "voice": "troy"}}}, "T2V_TTS__LANGUAGES"),
    ({"languages": {"en": {"model": VOICES["en"].model, "voice": "A b"}}}, "T2V_TTS__LANGUAGES"),
    ({"languages": {"xx": VOICES["en"]}}, "T2V_TTS__LANGUAGES"),
]


@pytest.mark.parametrize(("given", "setting"), REFUSED)
def test_built_in_code_it_refuses_what_settings_refuse(given: dict[str, Any], setting: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        GroqTTS(**(VALID | given))
    assert str(raised.value.details["setting"]).startswith(setting)
    assert "FIX: " in raised.value.message
    assert holding("made up", shown(raised.value)) == []
