"""GroqSTT against a fake Groq (plan 002, Track B): Block 0's baseline request, the result, a
cancel, each failure as a ProviderError, the key and the SDK's own variables kept out. Nothing
leaves the machine: a fake transport, or a server on 127.0.0.1. The prototype's call and tests
were read as specs, never run (Ole5-chatbot/src/ole5_chat/voice/stt.py, lines 221-252;
Ole5-chatbot/tests/test_voice_stt_v2.py, lines 324-337)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, get_args, get_type_hints

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.config import GroqSettings, Settings, SttSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText, Transcript

FIXTURE = Path(__file__).parents[1] / "fixtures" / "groq_stt_request.json"
BASELINE = json.loads(FIXTURE.read_text(encoding="utf-8"))
KEY, OTHER = "made-up-settings-key-0123", "made-up-shell-key-4567"
SETTING = "T2V_GROQ__API_KEY"
# Block 0's fixed clip: 1 s at 16 kHz, sample i = (i * 97) % 4096 - 2048.
CLIP = AudioClip(pcm16=b"".join(struct.pack("<h", (i * 97) % 4096 - 2048) for i in range(16_000)))
SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 0.6, "avg_logprob": -0.2, "no_speech_prob": 0.1},
    {"id": 1, "start": 0.6, "end": 1.0, "avg_logprob": -0.5, "no_speech_prob": 0.3},
    {"id": 2, "start": 1.0, "end": 2.0},  # gives neither value: weighs in neither
]
ANSWER = {"text": "  made-up words ", "language": "Arabic", "segments": SEGMENTS, "x_groq": {}}
SENT = {"host", "accept", "accept-encoding", "connection", "user-agent", "content-type"}
SENT |= {"content-length", "authorization"}

Reply = httpx.Response | Exception | Callable[[httpx.Request], Awaitable[httpx.Response]]


class FakeGroq(httpx.AsyncBaseTransport):
    """Answers each request with its next reply, keeping every request it receives."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies) or [httpx.Response(200, json=ANSWER)]
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, httpx.Response) else await reply(request)


def settings(timeout_s: float = 6.0, **groq: Any) -> Settings:
    given = GroqSettings(**({"api_key": SecretStr(KEY)} | groq))
    return Settings(_env_file=None, env="test", groq=given, stt=SttSettings(timeout_s=timeout_s))


async def call(fake: httpx.AsyncBaseTransport, clip: AudioClip = CLIP, **given: Any) -> Transcript:
    language, prompt = given.pop("language", "ar"), given.pop("prompt", None)
    adapter = GroqSTT.from_settings(settings(**given), transport=fake)
    try:
        return await adapter.transcribe(clip, language=language, prompt=prompt)
    finally:
        await adapter.aclose()


def parts(request: httpx.Request) -> dict[str, tuple[dict[str, str], bytes]]:
    """The multipart body's parts by field name: each one's headers (lowercase names) and bytes."""
    kind, _, boundary = request.headers["content-type"].partition("; boundary=")
    chunks = request.content.split(b"--" + boundary.encode())
    assert (kind, chunks[0], chunks[-1]) == ("multipart/form-data", b"", b"--\r\n")
    found = {}
    for chunk in chunks[1:-1]:
        head, _, data = chunk.removeprefix(b"\r\n").removesuffix(b"\r\n").partition(b"\r\n\r\n")
        lines = [line.decode().split(": ", 1) for line in head.split(b"\r\n")]
        headers = {name.lower(): value for name, value in lines}
        found[headers["content-disposition"].split('"')[1]] = (headers, data)
    return found


def test_the_request_is_block_0s_baseline() -> None:
    call_, want, client = BASELINE["call"], BASELINE["request"], BASELINE["client"]
    defaults = (GroqSettings().base_url, SttSettings().model, SttSettings().timeout_s)
    assert defaults == tuple(call_["settings"].values())  # the baseline's are the defaults
    fake = FakeGroq()
    asyncio.run(call(fake, language=call_["language"], prompt=call_["prompt"]))
    (request,) = fake.requests
    assert (request.method, str(request.url)) == (want["method"], want["url"])
    found = parts(request)
    file, wav = found.pop(want["file"]["field"])
    assert {name: data.decode() for name, (_, data) in found.items()} == want["fields"]
    assert not set(want["absent_fields"]) & set(found)
    assert file["content-disposition"].endswith(f'filename="{want["file"]["filename"]}"')
    assert file["content-type"] == want["file"]["content_type"]
    sha = hashlib.sha256(wav).hexdigest()
    assert (len(wav), sha) == (want["file"]["bytes"], BASELINE["clip"]["wav_sha256"])
    phases = ("connect", "read", "write", "pool")
    assert request.extensions["timeout"] == dict.fromkeys(phases, client["timeout_s"])
    assert set(request.headers) == SENT
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
    assert int(request.headers["content-length"]) == len(request.content)


@pytest.mark.parametrize(("seconds", "billed"), [(0.5, 10.0), (10.0, 10.0), (12.5, 12.5)])
def test_the_result_billed_10_s_or_more(seconds: float, billed: float) -> None:
    clip = AudioClip(pcm16=b"\x00\x00" * int(seconds * 16_000))
    result = asyncio.run(call(FakeGroq(), clip))
    assert (result.text, result.language, result.billed_seconds) == ("made-up words", "ar", billed)
    assert result.confidence == pytest.approx(0.6 * -0.2 + 0.4 * -0.5)
    assert result.no_speech_prob == pytest.approx(0.6 * 0.1 + 0.4 * 0.3)


@pytest.mark.parametrize("language", [None, ""])
def test_with_no_language_named_and_no_segment(language: str | None) -> None:
    fake = FakeGroq(httpx.Response(200, json={"text": "made-up", "language": "English"}))
    result = asyncio.run(call(fake, language=language, prompt="Made-up terms"))
    assert (result.language, result.confidence, result.no_speech_prob) == ("English", None, None)
    found = parts(fake.requests[0])
    assert "language" not in found and found["prompt"][1] == b"Made-up terms"


class Local(httpx.AsyncHTTPTransport):
    """Sends every request over a real connection to a server on 127.0.0.1, at `port`."""

    port, closed = 0, False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.url = request.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        return await super().handle_async_request(request)

    async def aclose(self) -> None:
        await super().aclose()
        self.closed = True


def test_a_cancel_ends_the_request_at_once_and_closes_its_connection() -> None:
    """The design's 6.1: in 50 ms, leaving no task and no connection; the server never answers."""
    listener = socket.create_server(("127.0.0.1", 0))
    listener.settimeout(5)
    accepted, hung_up = threading.Event(), threading.Event()

    def serve() -> None:
        with contextlib.suppress(OSError), listener.accept()[0] as connection:
            accepted.set()
            while connection.recv(65536):
                pass
            hung_up.set()

    async def scenario(transport: Local) -> tuple[float, bool, set[asyncio.Task[Any]], bool]:
        adapter = GroqSTT.from_settings(settings(), transport=transport)
        task = asyncio.create_task(adapter.transcribe(CLIP, language="ar", prompt=None))
        async with asyncio.timeout(5):
            while not accepted.is_set():
                await asyncio.sleep(0.001)
        await asyncio.sleep(0.05)  # the request is on the wire, its answer awaited
        start = time.perf_counter()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        took = time.perf_counter() - start
        left = asyncio.all_tasks() - {asyncio.current_task()}
        closed = await asyncio.to_thread(hung_up.wait, 5)  # before aclose: the cancel closed it
        await adapter.aclose()
        return took, task.cancelled(), left, closed

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    transport = Local()
    transport.port = listener.getsockname()[1]
    try:
        took, cancelled, left, closed = asyncio.run(scenario(transport))
    finally:
        listener.close()
        thread.join(5)
    assert (cancelled, left, closed, transport.closed) == (True, set(), True, True)
    assert took < 0.05, f"the cancel took {took * 1000:.1f} ms"


def _status(code: int, retry_after: str | None = None, **headers: str) -> httpx.Response:
    headers |= {} if retry_after is None else {"retry-after": retry_after}
    return httpx.Response(code, headers=headers, json={"error": {"message": "made-up"}})


async def _never(_request: httpx.Request) -> httpx.Response:
    await asyncio.sleep(3600)
    return httpx.Response(200, json=ANSWER)


BAD = ("server_error", False, None)  # an answer the adapter cannot read
NO_DELAY = (None, "Wed, 21 Oct 2026 07:28:00 GMT", "-3", "inf", "nan", "soon")
FAILURES = [
    *[(_status(429, value), "rate_limited", True, float(value)) for value in ("7", "1.5")],
    *[(_status(429, value), "rate_limited", True, None) for value in NO_DELAY],
    *[(_status(code), "server_error", True, None) for code in (500, 503, 409)],
    (_status(408), "timeout", True, None),
    *[(_status(code), "rejected", False, None) for code in (400, 401, 403, 404, 413, 422)],
    (_status(307, location="https://elsewhere.example/"), "rejected", False, None),
    (httpx.ReadTimeout("made-up"), "timeout", True, None),
    (_never, "timeout", True, None),  # past the test's 0.2 s: the adapter's own deadline
    (httpx.ConnectError("made-up"), "connection_lost", True, None),
    (httpx.RemoteProtocolError("made-up"), "connection_lost", True, None),
    (httpx.Response(200, text="made-up, no JSON"), *BAD),
    (httpx.Response(200, json={"segments": []}), *BAD),
    (httpx.Response(200, json={"text": "", "segments": [{"no_speech_prob": 2}]}), *BAD),
    (httpx.Response(200, json={"text": "", "segments": [{"avg_logprob": "x"}]}), *BAD),
]


@pytest.mark.parametrize(("reply", "kind", "retry", "delay"), FAILURES)
def test_each_failure_asked_once(reply: Reply, kind: str, retry: bool, delay: float | None) -> None:
    fake = FakeGroq(reply)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(call(fake, timeout_s=0.2))
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retry, delay)
    assert len(fake.requests) == 1  # no retry, no redirect followed
    assert (error.__cause__, error.__context__, error.__suppress_context__) == (None, None, True)
    if isinstance(reply, httpx.Response) and reply.status_code != 200:
        assert error.details["status"] == reply.status_code


@pytest.mark.parametrize("code", [400, 401, 429, 500])
def test_the_key_is_in_no_error_or_log_line_even_when_echoed(
    code: int, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    async def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"error": {"message": f"{dict(request.headers)}"}})

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(call(FakeGroq(echo)))
    error = raised.value
    assert any(record.name.startswith("groq") for record in caplog.records)  # the SDK's debug
    shown = [str(error), repr(error), json.dumps(error.details), caplog.text, *capsys.readouterr()]
    shown += ["".join(traceback.format_exception(error)), *(r.getMessage() for r in caplog.records)]
    assert [text for text in shown if KEY in text] == []


def _shown(request: httpx.Request) -> list[tuple[str, str]]:
    """The headers but the boundary and the length it sets: httpx draws a new boundary for every
    request, and takes a lowercase `content-type` line's; the hook keeps both the body's own."""
    assert int(request.headers["content-length"]) == len(request.content)
    pairs = request.headers.multi_items()
    return [(k, v.split("; boundary=")[0]) for k, v in pairs if k != "content-length"]


MANY = f"AUTHORIZATION: Bearer {OTHER}\nx-made-up: 1\nHost: elsewhere.example\nContent-Length: 3"
MANY += "\nUser-Agent: made-up\nAccept: text/plain\nConnection: close\naccept-encoding: br"
SHELLS = [
    {"GROQ_API_KEY": OTHER, "GROQ_BASE_URL": "https://elsewhere.example"},
    {"GROQ_CUSTOM_HEADERS": f"authorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_CUSTOM_HEADERS": f"Authorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_CUSTOM_HEADERS": MANY + "\nX-Stainless-Lang: made-up"},
    {"GROQ_CUSTOM_HEADERS": "content-type: multipart/form-data; boundary=madeup"},
]


@pytest.mark.parametrize("shell", SHELLS)
def test_the_sdks_own_variables_change_nothing(
    shell: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plain, shelled, path = FakeGroq(), FakeGroq(), tmp_path / "key.txt"
    asyncio.run(call(plain))
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    path.write_text(f"{KEY}\n", encoding="utf-8")
    asyncio.run(call(shelled, api_key=None, api_key_file=path))  # the same key, from its file
    (want,), (got,) = plain.requests, shelled.requests
    assert got.headers.get_list("authorization") == [f"Bearer {KEY}"]
    assert "x-made-up" not in got.headers and str(got.url) == BASELINE["request"]["url"]
    assert _shown(got) == _shown(want)
    assert [data for _, data in parts(got).values()] == [data for _, data in parts(want).values()]


_CHILD = """
import json, logging, sys
def state():
    levels = [logging.getLogger(name).level for name in ("groq", "httpx")]
    return [len(logging.getLogger().handlers), *levels]
before = state()
import {module}
print(json.dumps({{"imported": "groq" in sys.modules, "before": before, "after": state()}}))
"""
Imported = dict[tuple[str, str | None], dict[str, Any]]
ADAPTER = "t2_agentic_voice.groq"
CASES = [("groq", "debug"), (ADAPTER, None), (ADAPTER, "debug"), (ADAPTER, "info")]


@pytest.fixture(scope="module")
def imported() -> Imported:
    """What importing each module does to logging, each in a child whose shell sets `GROQ_LOG`
    alone of what tests/conftest.py drops; side by side, since importing groq takes seconds."""
    dropped = ("GROQ_", "OTEL_", "PHOENIX_", "T2V_")
    shell = {k: v for k, v in os.environ.items() if not k.upper().startswith(dropped)}
    running = {
        (module, level): subprocess.Popen(
            [sys.executable, "-c", _CHILD.format(module=module)],
            env=shell | ({"GROQ_LOG": level} if level else {}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for module, level in CASES
    }
    seen: Imported = {}
    for case, child in running.items():
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0, err.decode("utf-8", errors="replace")
        seen[case] = json.loads(out)
        assert seen[case]["imported"]
    return seen


def test_groq_log_is_read_and_the_adapter_alone_changes_nothing(imported: Imported) -> None:
    """The control: the child's variable is read, so the test below can see its effect."""
    seen = imported["groq", "debug"]
    assert seen["after"] == [seen["before"][0] + 1, logging.DEBUG, logging.DEBUG]
    assert imported[ADAPTER, None]["after"] == imported[ADAPTER, None]["before"]


@pytest.mark.parametrize("level", ["debug", "info"])
def test_groq_log_changes_nothing_on_the_adapters_import(level: str, imported: Imported) -> None:
    assert imported[ADAPTER, level]["after"] == imported[ADAPTER, level]["before"]


@pytest.mark.parametrize("file_text", [None, "", " \n"])
@pytest.mark.parametrize("key", [None, "", "   "])
def test_no_key_in_the_settings_is_a_configuration_error(
    key: str | None, file_text: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", OTHER)  # never read (the design's 7.3)
    (path := tmp_path / "key.txt").write_text(file_text or "", encoding="utf-8")
    given: dict[str, Any] = {"api_key": None if key is None else SecretStr(key)}
    given |= {"api_key_file": None if file_text is None else path}
    with pytest.raises(ConfigurationError, match=SETTING) as raised:
        GroqSTT.from_settings(settings(**given))
    assert raised.value.details == {"setting": SETTING}


URLS = ("http://api.groq.com", "https://made:up@api.groq.com", "https://api.groq.com?made=up")
MORE_URLS = ("https://api.groq.com#made-up", "https://", "https://api.groq.com:99999", "https://[x")
REFUSED = [
    *[({"api_key": SecretStr(key)}, SETTING) for key in (" ", "made up", "made-up-é", "a\nb")],
    ({"model": "whisper-1"}, "T2V_STT__MODEL"),
    *[({"base_url": url}, "T2V_GROQ__BASE_URL") for url in URLS + MORE_URLS],
    *[({"timeout_s": value}, "T2V_STT__TIMEOUT_S") for value in (0.0, -1.0, math.inf, math.nan)],
]


@pytest.mark.parametrize(("given", "setting"), REFUSED)
def test_built_in_code_it_refuses_what_settings_refuse(given: dict[str, Any], setting: str) -> None:
    valid: dict[str, Any] = {"api_key": SecretStr(KEY), "model": "whisper-large-v3"}
    valid |= {"base_url": "https://api.groq.com", "timeout_s": 6.0}
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT(**(valid | given))
    assert raised.value.details == {"setting": setting}
    if "api_key" in given and given["api_key"].get_secret_value().strip():
        assert given["api_key"].get_secret_value() not in str(raised.value)


def test_a_speech_to_text_with_no_key_in_its_repr_and_no_groq_type_in_its_signatures() -> None:
    """The design's 5.3 (no public signature names a `groq` type) and 6.1 (the data flow)."""
    adapter = GroqSTT.from_settings(settings())
    port: SpeechToText = adapter  # mypy checks the port's shape
    assert [text for text in (repr(adapter), repr(vars(adapter))) if KEY in text] == []
    want = "GroqSTT(model='whisper-large-v3', base_url='https://api.groq.com', timeout_s=6.0)"
    assert repr(adapter) == want
    asyncio.run(adapter.aclose())
    flow = port.data_flow
    assert (port.name, flow.provider) == ("groq", "Groq")
    assert flow.processed_in == "not stated by the provider"
    assert flow.stored_in == "US (Google Cloud buckets), for data Groq retains"
    assert flow.retention.startswith("none by default for inference; reliability and abuse logs")

    def modules(hint: object) -> set[str]:  # of a type, and of every type inside it
        return {getattr(hint, "__module__", "")}.union(*(modules(a) for a in get_args(hint)))

    public = [getattr(GroqSTT, n) for n in ("__init__", "from_settings", "transcribe", "aclose")]
    named = set().union(*(modules(h) for f in public for h in get_type_hints(f).values()))
    assert "httpx" in named and not [name for name in named if name.split(".")[0] == "groq"]
