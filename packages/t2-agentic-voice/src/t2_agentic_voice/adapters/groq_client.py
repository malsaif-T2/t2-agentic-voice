"""The Groq SDK's client as every Groq adapter builds it (D-004): `GroqSTT` (Whisper) and
`GroqTTS` (Orpheus) share it, each with its own request body and headers' values.

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
  shape it.
- Every exception the SDK raises becomes a `ProviderError` (`failure`), raised after the
  handler and from None, so no exception chain leads to the SDK's error, which holds the request
  and its headers. A cancel is never caught: the request ends at once and its connection is
  closed.
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
from collections.abc import Awaitable, Callable

import httpx
from pydantic import JsonValue, SecretStr, ValidationError

from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.logging import logging_unchanged
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.groq import KEY_FILE_SETTING, KEY_SETTING, GroqSettings
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

with logging_unchanged("groq", "httpx"):  # groq reads GROQ_LOG on import (TD-003)
    # Re-exported (`as`) for the adapters, which import the SDK only through this module.
    from groq import APIConnectionError as APIConnectionError
    from groq import APIStatusError as APIStatusError
    from groq import APITimeoutError as APITimeoutError
    from groq import AsyncGroq as AsyncGroq
    from groq import __version__ as groq_version
    from groq import omit as omit

# The prototype's connection pool (its `groqhttp.py`, read 2026-11-01): a connection is kept open
# five minutes, since httpx's 5 s left every utterance paying a new TLS handshake.
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=300.0)
# What the SDK sends as its own user agent (`AsyncGroq/Python <version>`).
USER_AGENT = f"AsyncGroq/Python {groq_version}".encode("ascii")
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
    """An adapter's request hook: every request carries these eight headers and no other, each
    with the adapter's value, in whatever case the SDK or `GROQ_CUSTOM_HEADERS` named them,
    `Accept` and `Content-Type` the ones given here. A body that does not open with `opens_with`
    was built some other way than the adapter's (a `content-type` line's boundary, or a form
    instead of JSON), and is never sent: ForeignBodyError(`refusal`). The length is the body's."""

    async def hook(request: httpx.Request) -> None:
        body = await request.aread()
        if not body.startswith(opens_with):
            raise ForeignBodyError(refusal)
        key = api_key.get_secret_value().encode("ascii")
        request.headers = httpx.Headers(
            {
                b"Host": request.url.netloc,
                b"Accept": accept,
                b"Accept-Encoding": b"gzip, deflate",
                b"Connection": b"keep-alive",
                b"User-Agent": USER_AGENT,
                b"Content-Type": content_type,
                b"Content-Length": str(len(body)).encode("ascii"),
                b"Authorization": b"Bearer " + key,
            }
        )

    return hook


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
