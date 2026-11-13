"""The Groq client every Groq adapter builds (adapters/groq_client.py), shown
on a JSON request, the kind `GroqTTS` sends: every request carries the adapter's own eight
headers whatever `GROQ_CUSTOM_HEADERS` says, and a `content-type` line that makes the SDK build a
form instead of the adapter's JSON fails the request, unsent, with no key in anything shown; on
a GET of the model list through the same client and hook, which carries six, with no body, and
goes through under the line that fails a POST; the SDK's raw-response marker, kept for the
adapter's own raw call alone; and an answer's `Date`, read strictly. `GroqSTT`'s use of it is
tested in test_groq_stt.py and test_groq_stt_checks.py. A fake transport only: nothing leaves the
machine."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
from groq._constants import RAW_RESPONSE_HEADER
from pydantic import SecretStr
from t2_agentic_voice.adapters.groq_client import (
    RAW_MARKER,
    APIConnectionError,
    AsyncGroq,
    ForeignBodyError,
    failure,
    groq_client,
    own_headers,
    raw_response,
    server_time,
)

from tests.leaks import holding, shown
from tests.t2_agentic_voice.adapters.groq_support import KEY, OTHER, FakeGroq

LISTED = {"host", "accept", "accept-encoding", "connection", "user-agent", "authorization"}
SENT = LISTED | {"content-type", "content-length"}
MODEL_ID = "canopylabs/orpheus-v1-english"
MODEL = {"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "made-up"}
FIELDS = {"model": "canopylabs/orpheus-v1-english", "voice": "troy", "input": "made-up words"}
SHELLS = [
    {},
    {"GROQ_CUSTOM_HEADERS": f"Accept: text/plain\nauthorization: Bearer {OTHER}\nX-Made-Up: 1"},
    {"GROQ_API_KEY": OTHER, "GROQ_BASE_URL": "https://elsewhere.example"},
    # Another case adds a second content type beside the SDK's, so the SDK still sends JSON.
    {"GROQ_CUSTOM_HEADERS": "content-type: multipart/form-data"},
]
# The SDK's own case replaces its content type, and the SDK then builds a form.
FORM_LINES = ["Content-Type: multipart/form-data", "Content-Type: multipart/form-data; boundary=x"]
# A line naming the SDK's raw-response marker, which would have it hand every answer back raw.
MARKER_LINE = {"GROQ_CUSTOM_HEADERS": f"{RAW_RESPONSE_HEADER}: raw"}


def _client(fake: httpx.AsyncBaseTransport) -> AsyncGroq:
    """A JSON adapter's client on `fake`, as `GroqTTS` builds it."""
    hook = own_headers(
        SecretStr(KEY),
        accept=b"audio/wav",
        content_type=b"application/json",
        opens_with=b"{",
        refusal="foreign_body",
    )
    return groq_client(
        api_key=SecretStr(KEY),
        base_url="https://api.groq.com",
        timeout_s=6.0,
        hook=hook,
        transport=fake,
    )


async def _speak(fake: httpx.AsyncBaseTransport) -> None:
    """One speech request with `FIELDS`, as a JSON adapter's client sends it on `fake`."""
    client = _client(fake)
    try:
        await client.audio.speech.create(
            model=FIELDS["model"],
            voice=FIELDS["voice"],
            input=FIELDS["input"],
            response_format="wav",
        )
    finally:
        await client.close()


@pytest.mark.parametrize("shell", SHELLS)
def test_a_json_request_carries_only_the_adapters_headers(
    shell: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    fake = FakeGroq(httpx.Response(200, content=b"RIFF"))
    asyncio.run(_speak(fake))
    (request,) = fake.requests
    assert str(request.url) == "https://api.groq.com/openai/v1/audio/speech"
    assert set(request.headers) == SENT
    assert (request.headers["accept"], request.headers["content-type"]) == (
        "audio/wav",
        "application/json",
    )
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
    assert int(request.headers["content-length"]) == len(request.content)
    assert json.loads(request.content) == FIELDS | {"response_format": "wav"}


@pytest.mark.parametrize("line", FORM_LINES)
def test_a_content_type_line_that_makes_a_form_fails_the_request_unsent(
    line: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The SDK builds a multipart form when a header says so; the hook refuses the body, which
    does not open as JSON does, and `failure` names the hook's reason, never the body."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", line)
    fake = FakeGroq()
    with pytest.raises(APIConnectionError) as raised:
        asyncio.run(_speak(fake))
    error = failure(raised.value)
    assert (error.kind, error.retryable, error.details) == (
        "rejected",
        False,
        {"error": "foreign_body"},
    )
    assert fake.requests == []
    assert holding(KEY, shown(error, caplog=caplog, capsys=capsys)) == []


@pytest.mark.parametrize(
    "shell", [*SHELLS, *({"GROQ_CUSTOM_HEADERS": line} for line in FORM_LINES), MARKER_LINE]
)
def test_a_get_through_the_same_client_carries_only_the_adapters_headers(
    shell: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model list and one model (`GroqTTS.check_language`, `t2v doctor`): the hook takes a
    request with no body, sends JSON as its `Accept`, and no `Content-Type` or length, so it
    goes through under the `content-type` line that fails a POST."""
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    listing = httpx.Response(200, json={"object": "list", "data": [MODEL]})
    fake = FakeGroq(listing, httpx.Response(200, json=MODEL))

    async def ask() -> None:
        client = _client(fake)
        try:
            listed = await client.models.list()
            assert [model.id for model in listed.data] == [MODEL_ID]  # parsed, never raw
            assert (await client.models.retrieve(MODEL_ID)).id == MODEL_ID
        finally:
            await client.close()

    asyncio.run(ask())
    assert [(r.method, r.url.path) for r in fake.requests] == [
        ("GET", "/openai/v1/models"),
        ("GET", f"/openai/v1/models/{MODEL_ID}"),
    ]
    for request in fake.requests:
        assert set(request.headers) == LISTED
        assert request.headers["accept"] == "application/json"
        assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
        assert request.content == b""


def test_a_request_with_no_body_that_carries_one_is_never_sent() -> None:
    hook = own_headers(
        SecretStr(KEY),
        accept=b"audio/wav",
        content_type=b"application/json",
        opens_with=b"{",
        refusal="foreign_body",
    )
    request = httpx.Request("GET", "https://api.groq.com/openai/v1/models", content=b"{}")

    async def send() -> None:
        await hook(request)

    with pytest.raises(ForeignBodyError) as raised:
        asyncio.run(send())
    assert raised.value.reason == "foreign_body"
    assert request.headers.get("authorization") is None  # left as it was: never sent


def test_the_sdks_raw_marker_goes_only_with_the_adapters_own_raw_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker makes the SDK hand an answer back raw, with its headers (`GroqSTT` reads the
    headroom there): the hook keeps it, with the SDK's value, for a call through
    `with_raw_response` inside `raw_response` alone, never from `GROQ_CUSTOM_HEADERS`, and
    drops it from the same call outside, which the SDK then hands back parsed."""
    assert RAW_MARKER == RAW_RESPONSE_HEADER  # the installed SDK's name for it
    monkeypatch.setenv("GROQ_CUSTOM_HEADERS", MARKER_LINE["GROQ_CUSTOM_HEADERS"])
    listing = httpx.Response(200, json={"object": "list", "data": [MODEL]}, headers={"x-a": "1"})
    fake = FakeGroq(listing, listing, httpx.Response(200, content=b"RIFF"), listing)

    async def ask() -> None:
        client = _client(fake)
        try:
            with raw_response():
                raw = await client.models.with_raw_response.list()
            assert raw.headers["x-a"] == "1" and (await raw.parse()).data[0].id == MODEL_ID
            dropped: object = await client.models.with_raw_response.list()
            assert type(dropped).__name__ == "ModelListResponse"  # handed back parsed
            await client.audio.speech.create(model=MODEL_ID, voice="troy", input="made-up")
            assert (await client.models.list()).data[0].id == MODEL_ID
        finally:
            await client.close()

    asyncio.run(ask())
    marked = [request.headers.get_list(RAW_MARKER) for request in fake.requests]
    assert marked == [["raw"], [], [], []]


SENT_AT = datetime(2026, 11, 4, 9, 15, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "Wed, 04 Nov 2026 09:15:02 GMT",  # RFC 9110's IMF-fixdate, as Groq sends it
        "Wednesday, 04-Nov-26 09:15:02 GMT",  # its obsolete RFC 850 form
        "Wed, 04 Nov 2026 09:15:02 +0000",
    ],
)
def test_an_answers_date_in_gmt_is_when_groq_sent_it(value: str) -> None:
    sent = server_time(httpx.Headers({"date": value}))
    assert sent == SENT_AT and sent is not None and sent.utcoffset() is not None


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("date", "")],
        [("date", "made-up")],
        [("date", "Wed, 32 Nov 2026 09:15:02 GMT")],
        [("date", "Wed, 04 Nov 2026 24:15:02 GMT")],
        [("date", "Wed, 04 Nov 2026 09:15:02.5 GMT")],
        [("date", "Wed, 04 Nov 99999999999999999999 09:15:02 GMT")],  # past a C long
        [("date", "Wed, 04 Nov 2026 09:15:02 +9999")],  # an offset past a day
        [("date", "Wed, 04 Nov 2026 09:15:02 +0300")],  # not GMT
        [("date", "Wed, 04 Nov 2026 09:15:02 -0000")],  # read with no zone
        [("date", "Wed Nov  4 09:15:02 2026")],  # asctime: no zone
        [("date", "Wed, 04 Nov 2026 09:15:02 GMT, Wed, 04 Nov 2026 09:15:03 GMT")],
        [("date", "Wed, 04 Nov 2026 09:15:02 GMT"), ("date", "Wed, 04 Nov 2026 09:15:03 GMT")],
        [(b"date", "٤ Nov 2026 09:15:02 GMT".encode())],  # an Arabic-Indic digit
    ],
)
def test_no_date_or_one_that_is_not_an_http_date_in_gmt_is_none(
    headers: list[tuple[str, str]] | list[tuple[bytes, bytes]],
) -> None:
    assert server_time(httpx.Headers(headers)) is None
