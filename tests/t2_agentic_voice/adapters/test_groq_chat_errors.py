"""GroqChat's failures (adapters/groq_chat.py; plan 006, Track A) on a fake transport: every
failure a `ProviderError` with its kind, `retryable` and `retry_after_s`, asked once (a 429 with
its `retry-after`, a 5xx, a timeout, a lost connection, a 4xx, an answer it cannot read); an
error Groq sends inside the stream (`tool_use_failed`) `rejected` with its code, never a silent
end; a `content-type` line that makes a form failing the request unsent; and the key in no error
or log line, even when echoed. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.chat_model import TextDelta

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.chat_support import (
    ask,
    ask_partly,
    call_piece,
    chunk,
    sse,
    streamed,
    text,
)
from tests.t2_agentic_voice.adapters.groq_support import KEY, FakeGroq

Reply = httpx.Response | Exception


def _status(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {} if retry_after is None else {"retry-after": retry_after}
    return httpx.Response(status, headers=headers, json={"error": {"message": "made-up"}})


BAD = ("server_error", False, None)  # an answer the adapter cannot read
FAILURES: list[tuple[Reply, str, bool, float | None]] = [
    (_status(429, "1"), "rate_limited", True, 1.0),
    (_status(429, "2.5"), "rate_limited", True, 2.5),
    (_status(429), "rate_limited", True, None),
    (_status(429, "Wed, 04 Nov 2026 09:15:02 GMT"), "rate_limited", True, None),
    *[(_status(code), "server_error", True, None) for code in (500, 502, 503, 409)],
    (_status(408), "timeout", True, None),
    *[(_status(code), "rejected", False, None) for code in (400, 401, 403, 404, 413, 422)],
    (httpx.ReadTimeout("made-up"), "timeout", True, None),
    (httpx.ConnectError("made-up"), "connection_lost", True, None),
    # The SDK does not wrap a failure while the answer streams.
    (streamed(sse(*text("Hi"))[:40], fail=httpx.ReadTimeout("made-up")), "timeout", True, None),
    (
        streamed(sse(*text("Hi"))[:40], fail=httpx.RemoteProtocolError("made-up")),
        "connection_lost",
        True,
        None,
    ),
    (
        streamed(sse(*text("Hi"))[:40], fail=httpx.ReadError("made-up")),
        "connection_lost",
        True,
        None,
    ),
    (streamed(b"data: {not json}\n\n"), *BAD),
    (streamed(sse({"choices": [{"index": 0, "delta": {"content": 7}}]})), *BAD),
    (streamed(sse(chunk(finish="made_up_reason"))), *BAD),
    (streamed(sse(call_piece(0, name="search_help"), chunk(finish="tool_calls"))), *BAD),  # no id
    (
        streamed(sse(chunk(finish="stop", usage={"prompt_tokens": -1, "completion_tokens": 0}))),
        *BAD,
    ),
]


@pytest.mark.parametrize(("reply", "kind", "retry", "delay"), FAILURES)
def test_each_failure_asked_once(reply: Reply, kind: str, retry: bool, delay: float | None) -> None:
    fake = FakeGroq(reply)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(ask(fake))
    error = raised.value
    assert (error.kind, error.retryable, error.retry_after_s) == (kind, retry, delay)
    assert len(fake.requests) == 1  # no retry
    assert (error.__cause__, error.__context__, error.__suppress_context__) == (None, None, True)


def test_a_stream_that_ends_with_no_finish_reason_is_never_a_silent_end() -> None:
    fake = FakeGroq(streamed(sse(chunk({"content": "Open Settings"}))))
    seen, error = asyncio.run(ask_partly(fake))
    assert seen == [TextDelta(text="Open Settings")]
    assert error is not None
    assert (error.kind, error.retryable, error.details) == (
        "server_error",
        False,
        {"error": "no_finish"},
    )


# Groq's answer when a Llama model wrote its own function text (plan 006's spike), as an SSE
# `error` event, and the same error as a plain data line.
FAILED_GENERATION = '<function=search_help {"query": "made-up secret words"} </function>'
TOOL_USE_FAILED = {
    "error": {
        "message": "Failed to call a function. Please adjust your prompt.",
        "type": "invalid_request_error",
        "code": "tool_use_failed",
        "failed_generation": FAILED_GENERATION,
    }
}


@pytest.mark.parametrize("named", [True, False])
def test_an_error_inside_the_stream_is_rejected_with_its_code(
    named: bool, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    error_event = ("error", TOOL_USE_FAILED) if named else TOOL_USE_FAILED
    fake = FakeGroq(streamed(sse(chunk({"content": "Let me"}), error_event, done=False)))
    seen, error = asyncio.run(ask_partly(fake))
    assert seen == [TextDelta(text="Let me")]
    assert error is not None
    assert (error.kind, error.retryable, error.retry_after_s) == ("rejected", False, None)
    assert error.details == {"error": "stream_error", "code": "tool_use_failed"}
    shown_text = shown(error, caplog=caplog, capsys=capsys)
    assert holding("made-up secret words", shown_text) == []
    assert holding(KEY, shown_text) == []


@pytest.mark.parametrize(
    "code", [None, "Not A Plain Name", "x" * 65, 7, "tool_use_failed: made-up secret words"]
)
def test_an_error_code_that_is_not_a_plain_name_is_left_out(code: object) -> None:
    body = {"error": {"message": "made-up", "code": code}}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(ask(FakeGroq(streamed(sse(("error", body), done=False)))))
    assert (raised.value.kind, raised.value.details) == ("rejected", {"error": "stream_error"})


@pytest.mark.parametrize(
    "line", ["Content-Type: multipart/form-data", "Content-Type: multipart/form-data; boundary=x"]
)
def test_a_content_type_line_that_makes_a_form_fails_the_request_unsent(
    line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", line)
    fake = FakeGroq()
    with pytest.raises(ProviderError) as raised:
        asyncio.run(ask(fake))
    error = raised.value
    assert (error.kind, error.retryable, error.details) == (
        "rejected",
        False,
        {"error": "foreign_body"},
    )
    assert fake.requests == []


@pytest.mark.parametrize("code", [400, 401, 429, 500, 200])
def test_the_key_is_in_no_error_or_log_line_even_when_echoed(
    code: int, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal that echoes the request's headers, and (200) an error inside the stream that
    does: neither reaches the ProviderError, and the SDK's own debug lines hold no key."""

    async def echo(request: httpx.Request) -> httpx.Response:
        error = {"error": {"message": f"{dict(request.headers)}", "code": "made_up"}}
        if code != 200:
            return httpx.Response(code, json=error)
        return httpx.Response(200, content=sse(("error", error), done=False))

    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(ask(FakeGroq(echo)))
    assert any(record.name.startswith("groq") for record in caplog.records)  # the SDK's debug
    assert holding(KEY, shown(raised.value, caplog=caplog, capsys=capsys)) == []
