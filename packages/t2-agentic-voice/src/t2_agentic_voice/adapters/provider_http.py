"""What the adapters of the providers measured beside Groq share (D-100): each talks to its
provider by raw HTTPS through httpx, with no SDK, so nothing reads a variable of its own.

- `http_client`: the adapter's own HTTP client: its timeout, the shared connection limits, no
  redirect followed (it would carry the key to another host), and `trust_env` off, so no proxy,
  CA or `.netrc` variable sends the key, the audio or the transcript anywhere else.
- `http_failure`: every failure a `ProviderError` whose details hold the provider's name, the
  failure's class name and the HTTP status, if any: never the provider's text or body, which may
  echo the request, and never the key. A cancel is never caught.
- `provider_key`: the key its group of the settings gives (core/settings/provider_keys.py), or a
  ConfigurationError naming the variable to set, so an unavailable provider says so when chosen,
  and the Groq adapter to pick instead (`STT_INSTEAD`, or `TTS_INSTEAD` for a voice's).
- `keyterms`: the terms a prompt holds, for a provider that takes a list rather than a prompt.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import httpx
from pydantic import JsonValue, SecretStr

from t2_agentic_voice.adapters.groq_client import LIMITS, retry_after
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.provider_keys import ProviderKey


def http_client(
    *, timeout_s: float, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    """An adapter's HTTP client (the module's docstring); `transport` replaces the HTTP
    transport (a test's fake one). Close it with its `aclose()`."""
    return httpx.AsyncClient(
        transport=transport,
        limits=LIMITS,
        timeout=timeout_s,
        follow_redirects=False,
        trust_env=False,
    )


class AnswerError(Exception):
    """An answer the adapter cannot use, named by a fixed `reason` and nothing it held."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def ok_status(response: httpx.Response) -> httpx.Response:
    """`response` when its status is 2xx; else the HTTPStatusError `http_failure` maps."""
    if not response.is_success:
        raise httpx.HTTPStatusError("status", request=response.request, response=response)
    return response


def http_failure(provider: str, error: Exception) -> ProviderError:
    """The ProviderError for one failure (the module's docstring). A status is retryable where
    the Groq adapters' rule asks again (408, 409, 429 and 5xx); an answer the adapter cannot
    read, or any other failure, is a server error not worth asking again for."""
    details: dict[str, JsonValue] = {"provider": provider, "error": type(error).__name__}
    if isinstance(error, AnswerError):
        details["error"] = error.reason
        return ProviderError("server_error", False, details=details)
    if isinstance(error, httpx.TimeoutException | TimeoutError):
        return ProviderError("timeout", True, details=details)
    if isinstance(error, httpx.TransportError):
        return ProviderError("connection_lost", True, details=details)
    if not isinstance(error, httpx.HTTPStatusError):
        return ProviderError("server_error", False, details=details)
    response = error.response
    return status_failure(details, response.status_code, response.headers.get("retry-after"))


def status_failure(
    details: dict[str, JsonValue], status: int, retry_after_header: str | None
) -> ProviderError:
    """The ProviderError for a refused HTTP status (`http_failure`'s rule), `details` with the
    status added; a WebSocket handshake's refusal maps the same way."""
    details["status"] = status
    if status == 429:
        delay = retry_after(retry_after_header)
        return ProviderError("rate_limited", True, delay, details=details)
    if status == 408:
        return ProviderError("timeout", True, details=details)
    if status == 409 or status >= 500:
        return ProviderError("server_error", True, details=details)
    return ProviderError("rejected", False, details=details)


# What a provider chosen with no key may be swapped for: Groq's adapter, on the Groq key alone.
STT_INSTEAD: Final = (
    "pick another speech-to-text provider with stt.provider (groq, Whisper, needs only the Groq "
    "key)"
)
TTS_INSTEAD: Final = (
    "pick another text-to-speech provider with tts.provider (groq, Orpheus, needs only the Groq "
    "key)"
)


def provider_key(
    settings: VoiceSettings, group: ProviderKey, vendor: str, *, instead: str = STT_INSTEAD
) -> SecretStr:
    """The key `group` of `settings` gives, inline or in its file; a ConfigurationError naming
    its variable under the settings' prefix when none is set, a blank one included."""
    key = group.resolved_api_key(settings.prefix)
    if key is None:
        raise no_key(vendor, settings.env_name(group.GROUP, "api_key"), instead=instead)
    return key


def given_key(
    api_key: SecretStr, kind: type[ProviderKey], vendor: str, *, instead: str = STT_INSTEAD
) -> SecretStr:
    """A key given in code, held to the settings' rules (GP-20): its characters checked, the
    space around it removed; a ConfigurationError naming the setting when it is blank or holds
    a character no key holds, never the key."""
    key = kind(api_key=api_key).resolved_api_key()
    if key is None:
        raise no_key(vendor, setting_name(kind.GROUP, "api_key"), instead=instead)
    return key


def no_key(vendor: str, setting: str, *, instead: str = STT_INSTEAD) -> ConfigurationError:
    """The error for a provider chosen with no key: which variable to set."""
    return ConfigurationError(
        f"No {vendor} API key is set, so its adapter is unavailable. FIX: set {setting}, or "
        f"{setting}_FILE to a file that holds the key, or {instead}.",
        details={"setting": setting},
    )


def keyterms(prompt: str | None, *, most: int, longest: int) -> tuple[str, ...]:
    """The terms of `prompt`, as the library's speech-to-text prompt holds them (the agent's
    vocabulary then the command words, joined with commas; domain/whisper_prompt.py): each
    term with the space around it removed, each once, in order, at most `most` of them and each
    at most `longest` characters (a longer one left out); none for no prompt."""
    return tuple(_terms(prompt.split(",") if prompt else (), most=most, longest=longest))


def _terms(parts: Iterable[str], *, most: int, longest: int) -> list[str]:
    found: list[str] = []
    for part in parts:
        term = part.strip()
        if term and len(term) <= longest and term not in found:
            found.append(term)
    return found[:most]
