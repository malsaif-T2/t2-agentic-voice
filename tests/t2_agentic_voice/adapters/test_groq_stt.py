"""GroqSTT against a fake Groq: the baseline request, the result and
its headroom, a cancel, each failure as a ProviderError, the key and the SDK's own variables kept
out. Nothing
leaves the machine: a fake transport, or a server on 127.0.0.1. The prototype's call and tests
were read as specs, never run (Ole5-chatbot/src/ole5_chat/voice/stt.py, lines 221-252;
Ole5-chatbot/tests/test_voice_stt_v2.py, lines 324-337)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, get_args, get_type_hints

import httpx
import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_stt import GroqSTT
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText

from tests.isolation import dropped
from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import (
    ANSWER,
    BASELINE,
    CLIP,
    KEY,
    OTHER,
    SETTING,
    FakeGroq,
    Reply,
    call,
    groq_settings,
    parts,
)

SENT = {"host", "accept", "accept-encoding", "connection", "user-agent", "content-type"}
SENT |= {"content-length", "authorization", "x-stainless-raw-response"}  # the SDK's raw marker
REMAINING = ("x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens")
BOUNDARY = "made-up-boundary-0123456789abcdef"  # what `fixed_boundary` makes every adapter draw


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
    assert request.headers.get_list("x-stainless-raw-response") == ["raw"]
    assert int(request.headers["content-length"]) == len(request.content)


@pytest.mark.parametrize(
    ("sent", "headroom"),
    [
        ({REMAINING[0]: "13", REMAINING[1]: "5940"}, (13, 5940)),
        ({REMAINING[0]: "0", REMAINING[1]: "007"}, (0, 7)),
        ({}, (None, None)),  # absent
        ({REMAINING[0]: "14"}, (14, None)),
        ({REMAINING[0]: "-1", REMAINING[1]: "1.5"}, (None, None)),
        ({REMAINING[0]: "", REMAINING[1]: "x"}, (None, None)),
        ({REMAINING[0]: " 7", REMAINING[1]: "1_000"}, (None, None)),
        # Arabic-Indic digits, sent as UTF-8; more digits than Python converts.
        (
            {
                REMAINING[0].encode(): (chr(0x661) + chr(0x662)).encode(),
                REMAINING[1].encode(): b"9" * 5000,
            },
            (None, None),
        ),
    ],
)
def test_the_answers_headroom_rides_on_its_transcript(
    sent: dict[str, str] | dict[bytes, bytes], headroom: tuple[int | None, int | None]
) -> None:
    """Groq's rate-limit headers, read through the SDK's raw response: each a whole number in
    ASCII digits, else None (one a malformed header leaves out, or one Python cannot convert);
    the answer is parsed as before."""
    fake = FakeGroq(httpx.Response(200, json=ANSWER, headers=sent))
    result = asyncio.run(call(fake))
    assert (result.remaining_requests, result.remaining_tokens) == headroom
    assert (result.text, result.language) == ("made-up words", "ar")


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
        adapter = GroqSTT.from_settings(groq_settings(), transport=transport)
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
    assert holding(KEY, shown(error, caplog=caplog, capsys=capsys)) == []


@pytest.fixture
def fixed_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every adapter draws `BOUNDARY`, so two adapters' requests can be compared whole."""
    monkeypatch.setattr(secrets, "token_hex", lambda size: BOUNDARY)  # the adapter's draw


def _headers(request: httpx.Request) -> list[tuple[str, str]]:
    """The headers but the length, which the body's own sets; the boundary is the adapter's."""
    assert int(request.headers["content-length"]) == len(request.content)
    assert request.headers["content-type"] == f"multipart/form-data; boundary={BOUNDARY}"
    return [(k, v) for k, v in request.headers.multi_items() if k != "content-length"]


MANY = f"AUTHORIZATION: Bearer {OTHER}\nx-made-up: 1\nHost: elsewhere.example\nContent-Length: 3"
MANY += "\nUser-Agent: made-up\nAccept: text/plain\nConnection: close\naccept-encoding: br"
SHELLS = [
    {"GROQ_API_KEY": OTHER, "GROQ_BASE_URL": "https://elsewhere.example"},
    {"GROQ_CUSTOM_HEADERS": f"authorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_CUSTOM_HEADERS": f"Authorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_CUSTOM_HEADERS": MANY + "\nX-Stainless-Lang: made-up"},
    {"GROQ_CUSTOM_HEADERS": "Content-Type: multipart/form-data; boundary=madeup"},
    {"GROQ_CUSTOM_HEADERS": "X-Stainless-Raw-Response: stream"},  # the SDK's marker
]  # a content-type line in another case fails the request: test_groq_stt_checks.py


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.usefixtures("fixed_boundary")
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
    assert _headers(got) == _headers(want)
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
    alone of what the suite drops (tests/isolation.py); side by side, since importing groq takes
    seconds."""
    shell = {k: v for k, v in os.environ.items() if not dropped(k)}
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
        GroqSTT.from_settings(groq_settings(**given))
    assert raised.value.details == {"setting": SETTING}


@pytest.mark.parametrize("prefix", ["T2V_", "HELPDESK_VOICE_"])
def test_with_groq_api_key_set_instead_the_error_names_the_variable_to_set(
    prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The design's 7.3: the error names the variable to set, under the settings' prefix, and
    says the other is never read; neither its value nor the key reaches anything shown."""
    monkeypatch.setenv(f"{prefix}ENV", "test")
    monkeypatch.setenv("GROQ_API_KEY", OTHER)
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT.from_settings(VoiceSettings.from_env(prefix=prefix))
    assert raised.value.message == (
        "No Groq API key is set. GROQ_API_KEY is set, but the library never reads it. FIX: set "
        f"{prefix}GROQ__API_KEY, or {prefix}GROQ__API_KEY_FILE to a file that holds the key."
    )
    assert raised.value.details == {"setting": f"{prefix}GROQ__API_KEY"}
    assert holding(OTHER, shown(raised.value)) == []
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(ConfigurationError) as raised:
        GroqSTT.from_settings(VoiceSettings.from_env(prefix=prefix))
    assert "GROQ_API_KEY is set" not in raised.value.message


def test_a_speech_to_text_with_no_key_in_its_repr_and_no_groq_type_in_its_signatures() -> None:
    """The design's 5.3 (no public signature names a `groq` type) and 6.1 (the data flow)."""
    adapter = GroqSTT.from_settings(groq_settings())
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
