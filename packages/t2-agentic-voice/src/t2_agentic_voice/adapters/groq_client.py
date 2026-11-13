"""The Groq SDK's client as every Groq adapter builds it (D-004): `GroqSTT` (Whisper), `GroqChat`
(the chat models) and `GroqTTS` (Orpheus) share it, each with its own request body and headers'
values.

How it keeps to the design's 7.3 ("Other names are never read") and keeps the key out of
everything but the request, as plan 002's decision log reads groq 1.7.0
(tests/t2_agentic_voice/test_read_versions.py fails on another version):

- The key, `groq.base_url` and the timeout are always passed to the SDK, so it never falls back
  to `GROQ_API_KEY` or `GROQ_BASE_URL`. Its own retries are off: the caller asks again, and
  counts every attempt. No redirect is followed: it would carry the key to another host.
- The SDK reads `GROQ_CUSTOM_HEADERS` whatever is passed, and its lines sit over the
  `Authorization` header the SDK builds from the key. So the HTTP client an adapter gives it has
  a request hook (`own_headers`) that replaces every header with the adapter's own: a fixed
  list, each with a value the adapter sets, `Authorization` the settings' key. No line of that
  variable, in any case, adds a header, sends another key or a second one, or changes a header's
  value. A `content-type` line can change how the SDK and httpx build the body (a multipart
  boundary, or a form instead of JSON), so the hook refuses a body that does not open as the
  adapter's own does: such a line can only fail a request (a `rejected` ProviderError), never
  shape it. A request with no body (a GET: the model list, one model) goes through the same
  client and hook, with JSON as its `Accept`, no `Content-Type`, and no body at all.
- The SDK hands back an answer's headers (its rate-limit headroom, its `Date`) only in its raw
  response, which it gives when the request it sent carries its raw-response marker. The hook
  keeps that marker only for the adapter's own call that asks for it (`raw_response` around a
  call through `with_raw_response`), never from `GROQ_CUSTOM_HEADERS` or the environment, so no
  line of that variable changes what the SDK hands back.
- Every exception the SDK raises becomes a `ProviderError` (`failure`), raised after the
  handler and from None, so no exception chain leads to the SDK's error, which holds the request
  and its headers; a streamed answer's read that times out or loses its connection, which the
  SDK does not wrap, is `timeout` or `connection_lost` (`stream_failure`). A cancel is never
  caught: the request ends at once and its connection is closed.
- The key an adapter's `from_settings` takes is the settings' (`settings_key`): inline or in
  its file, and a ConfigurationError naming the variable under the settings' prefix when none
  is set.
- `GROQ_LOG`, which `groq` reads when it is imported, is undone: `groq` is imported here alone,
  inside `core.logging.logging_unchanged`, which removes the root handler the SDK adds and puts
  the `groq` and `httpx` loggers' levels back (only `core` may import `logging`, ARCH-OWNER). An
  adapter imports the SDK's names from this module, never from `groq`, so the import stays
  inside that guard whatever the import order. An app that imports `groq` before the library
  keeps the variable's effect (TD-003).

The SDK's types stay inside the adapters; no public signature names one (the design's 5.3).
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from pydantic import JsonValue, SecretStr, ValidationError

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.logging import logging_unchanged
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.groq import KEY_FILE_SETTING, KEY_SETTING, GroqSettings
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

with logging_unchanged("groq", "httpx"):  # groq reads GROQ_LOG on import (TD-003)
    # Re-exported (`as`) for the adapters, which import the SDK only through this module.
    from groq import APIConnectionError as APIConnectionError
    from groq import APIError as APIError
    from groq import APIStatusError as APIStatusError
    from groq import APITimeoutError as APITimeoutError
    from groq import AsyncGroq as AsyncGroq
    from groq import Omit as Omit
    from groq import __version__ as groq_version
    from groq import omit as omit
    from groq.types.chat import (
        ChatCompletionAssistantMessageParam as ChatCompletionAssistantMessageParam,
    )
    from groq.types.chat import ChatCompletionMessageParam as ChatCompletionMessageParam
    from groq.types.chat import ChatCompletionToolParam as ChatCompletionToolParam

# The prototype's connection pool (its `groqhttp.py`, read 2026-11-01): a connection is kept open
# five minutes, since httpx's 5 s left every utterance paying a new TLS handshake.
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=300.0)
# What the SDK sends as its own user agent (`AsyncGroq/Python <version>`).
USER_AGENT = f"AsyncGroq/Python {groq_version}".encode("ascii")
# The methods whose requests send a body; Groq answers every other (a GET) in JSON.
_SENDS_BODY = frozenset({"POST", "PUT", "PATCH"})
_JSON = b"application/json"
# The SDK's marker of a call that asks for its raw response, and the value its
# `with_raw_response` gives it (groq 1.7.0: `RAW_RESPONSE_HEADER` in groq/_constants.py, and
# groq/_response.py's wrappers); the SDK reads it back from the request as it was sent.
RAW_MARKER = "X-Stainless-Raw-Response"
_RAW = b"raw"
# Whether the adapter's own call, now, asked for the raw response (`raw_response`).
_ASKED_RAW: ContextVar[bool] = ContextVar("t2v_groq_raw_response", default=False)
# The headroom Groq reports with an answer: the requests and the tokens left to the key.
_REMAINING = ("x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens")
# Groq's "Your Data" page, as the design's 6.1 gives it.
DATA_FLOW = DataFlow(
    provider="Groq",
    processed_in="not stated by the provider",
    stored_in="US (Google Cloud buckets), for data Groq retains",
    retention=(
        "none by default for inference; reliability and abuse logs up to 30 days unless Zero "
        "Data Retention is on or log storage is opted out"
    ),
)

RequestHook = Callable[[httpx.Request], Awaitable[None]]
# A settings group's check, by its name in the settings (`stt`, `tts`): it builds the group
# from the values an adapter was given, raising ValidationError for one the settings refuse.
GroupCheck = tuple[str, Callable[[], object]]


class ForeignBodyError(Exception):
    """A body the request hook refused, never sent: it does not open as the adapter's own does.
    It holds no value, only `reason`, a fixed name the adapter gave: the SDK logs it at DEBUG,
    with its traceback, as it wraps it in an APIConnectionError."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def own_headers(
    api_key: SecretStr, *, accept: bytes, content_type: bytes, opens_with: bytes, refusal: str
) -> RequestHook:
    """An adapter's request hook: every request carries the adapter's headers and no other, each
    with the adapter's value, in whatever case the SDK or `GROQ_CUSTOM_HEADERS` named them. A
    request that sends a body (POST, PUT, PATCH) carries eight, `Accept` and `Content-Type` the
    ones given here and the length the body's; a body that does not open with `opens_with` was
    built some other way than the adapter's (a `content-type` line's boundary, or a form
    instead of JSON), and is never sent: ForeignBodyError(`refusal`). Any other request (a GET
    of the model list) carries six, JSON its `Accept`, with no `Content-Type` or length, and
    one with a body is never sent either. The adapter's own call inside `raw_response` that
    asks for the raw response carries one more, the SDK's marker (`RAW_MARKER`) with the SDK's
    value; every other request goes without it, whatever the SDK was given."""

    async def hook(request: httpx.Request) -> None:
        body = await request.aread()
        sends_body = request.method in _SENDS_BODY
        foreign = not body.startswith(opens_with) if sends_body else body != b""
        if foreign:
            raise ForeignBodyError(refusal)
        key = api_key.get_secret_value().encode("ascii")
        headers = {
            b"Host": request.url.netloc,
            b"Accept": accept if sends_body else _JSON,
            b"Accept-Encoding": b"gzip, deflate",
            b"Connection": b"keep-alive",
            b"User-Agent": USER_AGENT,
        }
        if sends_body:
            headers[b"Content-Type"] = content_type
            headers[b"Content-Length"] = str(len(body)).encode("ascii")
        if _ASKED_RAW.get() and RAW_MARKER in request.headers:
            headers[RAW_MARKER.encode("ascii")] = _RAW
        headers[b"Authorization"] = b"Bearer " + key
        request.headers = httpx.Headers(headers)

    return hook


@contextmanager
def raw_response() -> Iterator[None]:
    """Inside it, the adapter's own call through the SDK's `with_raw_response` gets the raw
    response, which holds the answer's headers (`headroom`): the request hook keeps the SDK's
    marker that asks for it there alone. Elsewhere the hook drops the marker, so a
    `GROQ_CUSTOM_HEADERS` line that names it never changes what the SDK hands back."""
    asked = _ASKED_RAW.set(True)
    try:
        yield
    finally:
        _ASKED_RAW.reset(asked)


def headroom(headers: httpx.Headers) -> tuple[int | None, int | None]:
    """The rate-limit headroom an answer reports for the key, the requests and the tokens left
    (Groq's `x-ratelimit-remaining-requests` and `-tokens`): each a whole number written in
    ASCII digits, else None, as for a header that is absent."""
    requests, tokens = (_count(headers.get(name)) for name in _REMAINING)
    return requests, tokens


def server_time(headers: httpx.Headers) -> datetime | None:
    """When Groq sent an answer, from its one `Date` header (RFC 9110's HTTP-date: whole
    seconds, in GMT), aware in UTC. None, never an error, for no `Date`, more than one, or one
    `email.utils.parsedate_to_datetime` does not read as a time in GMT: a value outside ASCII,
    one it refuses, and one it reads with no zone or another zone (two values joined by a comma,
    `-0000`, an asctime date), since an HTTP date is always GMT."""
    values = headers.get_list("date")
    if len(values) != 1 or not values[0].isascii():
        return None
    try:
        sent = parsedate_to_datetime(values[0])
    except (ValueError, OverflowError):  # a date it cannot read, or a year past a C long
        return None
    return sent if sent.utcoffset() == timedelta(0) else None


def _count(value: str | None) -> int | None:
    """`value` as a whole number when it is ASCII digits alone, else None."""
    if value is None or not (value.isascii() and value.isdigit()):
        return None
    try:
        return int(value)
    except ValueError:  # more digits than Python converts (sys.get_int_max_str_digits)
        return None


def groq_client(
    *,
    api_key: SecretStr,
    base_url: str,
    timeout_s: float,
    hook: RequestHook,
    transport: httpx.AsyncBaseTransport | None,
) -> AsyncGroq:
    """The SDK's client for one adapter: the key, `base_url` and the timeout passed, its own
    retries off, on an HTTP client of its own with the shared connection limits, following no
    redirect, and `hook` (the adapter's `own_headers`) on every request. `transport` replaces
    the HTTP transport (a test's fake one). Close it with its `close()`."""
    key = api_key.get_secret_value()
    http = httpx.AsyncClient(
        transport=transport,
        limits=LIMITS,
        timeout=timeout_s,
        follow_redirects=False,  # a redirect would carry the key to another host
        event_hooks={"request": [hook]},
    )
    return AsyncGroq(
        api_key=key,
        base_url=base_url,
        timeout=timeout_s,
        max_retries=0,
        default_headers={"Authorization": f"Bearer {key}"},
        http_client=http,
    )


def failure(error: Exception) -> ProviderError:
    """The ProviderError for one failure. Its details hold the failure's class name and the HTTP
    status, if any: never the SDK's message or body, which may echo the request. A status is
    retryable where the SDK's own retry rule would ask again (408, 409, 429 and 5xx); an answer
    that cannot be read, or any other failure, is a server error not worth asking again for; a
    body the hook refused, never sent, is rejected, named by the hook's reason."""
    details: dict[str, JsonValue] = {"error": type(error).__name__}
    if isinstance(error, APIConnectionError) and isinstance(error.__cause__, ForeignBodyError):
        details["error"] = error.__cause__.reason  # never sent: asking again fails the same way
        return ProviderError("rejected", False, details=details)
    if isinstance(error, APITimeoutError | TimeoutError):
        return ProviderError("timeout", True, details=details)
    if isinstance(error, APIConnectionError):
        return ProviderError("connection_lost", True, details=details)
    if not isinstance(error, APIStatusError):
        return ProviderError("server_error", False, details=details)
    status = error.status_code
    details["status"] = status
    if status == 429:
        delay = retry_after(error.response.headers.get("retry-after"))
        return ProviderError("rate_limited", True, delay, details=details)
    if status == 408:
        return ProviderError("timeout", True, details=details)
    if status == 409 or status >= 500:
        return ProviderError("server_error", True, details=details)
    return ProviderError("rejected", False, details=details)


def stream_failure(error: Exception) -> ProviderError:
    """`failure`, and the httpx errors a streamed answer's read raises, which the SDK wraps only
    while it sends: a timeout is `timeout`, any other transport error `connection_lost`, each
    named by its class alone."""
    if isinstance(error, httpx.TimeoutException):
        return ProviderError("timeout", True, details={"error": type(error).__name__})
    if isinstance(error, httpx.TransportError):
        return ProviderError("connection_lost", True, details={"error": type(error).__name__})
    return failure(error)


def retry_after(value: str | None) -> float | None:
    """The delay a `retry-after` header asks for, in seconds; None unless it is a finite number of
    seconds, 0 or more (an HTTP date is not read)."""
    try:
        seconds = float(value or "")
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def no_key(
    setting: str = KEY_SETTING, file_setting: str = KEY_FILE_SETTING, other_set: bool = False
) -> ConfigurationError:
    """The error for a missing key, naming the variable to set; when GROQ_API_KEY is set, it
    says the library never reads that one (the design's 7.3)."""
    unread = " GROQ_API_KEY is set, but the library never reads it." if other_set else ""
    return ConfigurationError(
        f"No Groq API key is set.{unread} FIX: set {setting}, or {file_setting} to a file that "
        "holds the key.",
        details={"setting": setting},
    )


def settings_key(settings: VoiceSettings) -> SecretStr:
    """The key the settings give (`groq.resolved_api_key()`, inline or in its file): a
    ConfigurationError naming `T2V_GROQ__API_KEY` (under the settings' prefix) when none is set,
    a blank one included, saying so when `GROQ_API_KEY` is set instead (`no_key`)."""
    key = settings.groq.resolved_api_key(settings.prefix)
    if key is None:
        raise no_key(
            settings.env_name("groq", "api_key"),
            settings.env_name("groq", "api_key_file"),
            settings.saw("GROQ_API_KEY"),
        )
    return key


def checked(api_key: SecretStr, base_url: str, *groups: GroupCheck) -> SecretStr:
    """The key, as `GroqSettings.resolved_api_key` gives it, once the settings' own models take
    every value: for a team that builds an adapter in code, the constructor refuses what the
    settings refuse as they load, by the same rules (GP-20): the `groq` group's key and base
    URL, then each of the adapter's own `groups`. Each error names the setting and never the
    value; it is raised outside the handler, so no exception chain leads to it."""
    checks: tuple[GroupCheck, ...] = (
        ("groq", lambda: GroqSettings(api_key=api_key, base_url=base_url)),
        *groups,
    )
    for group, check in checks:
        try:
            check()
        except ValidationError as error:
            problem = error.errors(include_input=False, include_url=False)[0]
        else:
            continue
        setting = setting_name(group, *problem["loc"])
        raise ConfigurationError(
            f"The Groq adapter refuses its {setting} ({problem['msg']}). FIX: give it a value "
            "the settings take.",
            details={"setting": setting},
        )
    key = GroqSettings(api_key=api_key).resolved_api_key()
    if key is None:
        raise no_key()
    return key
