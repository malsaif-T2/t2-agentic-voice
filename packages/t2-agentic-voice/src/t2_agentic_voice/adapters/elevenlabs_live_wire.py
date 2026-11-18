"""What ElevenLabs' realtime speech-to-text sends and takes (adapters/elevenlabs_live.py, plan
010's 5.1), from its API reference and event reference (read 2026-11-18):

- `live_url`: the endpoint, `/v1/speech-to-text/realtime` under the adapter's base URL (its
  `https` as `wss`), and its query: `model_id`, `audio_format` (`pcm_<rate>`, one of `RATES`),
  `commit_strategy=manual`, the call's `language_code`, `include_language_detection` (as the
  probe of 2026-11-18 sent it) and each keyterm, at most `MOST_KEYTERMS` of at most
  `LONGEST_KEYTERM` characters, realtime's limits;
- `audio_message`: an `input_audio_chunk` (base64 PCM, `commit`, the sample rate); a commit is
  one with empty audio and `commit` true, the docs' raw WebSocket example;
- `read_message` and `check_message`: a server message parsed at the boundary, and an error
  message (`ERRORS`, which the server sends before it closes) raised as `RefusedError`;
- `live_failure`: every failure of a stream a ProviderError naming the provider and the error's
  type (`_KINDS`), never its text, the key, the audio or a transcript.
"""

from __future__ import annotations

import base64
import json
from typing import Final
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from t2_agentic_voice.adapters.provider_http import AnswerError
from t2_agentic_voice.adapters.provider_socket import socket_failure
from t2_agentic_voice.core.errors import ProviderError, ProviderErrorKind

NAME: Final = "elevenlabs"
LIVE_MODEL: Final = "scribe_v3_live"
REALTIME_PATH: Final = "/v1/speech-to-text/realtime"
MOST_KEYTERMS: Final = 50
LONGEST_KEYTERM: Final = 20
# The sample rates realtime takes as `pcm_<rate>`.
RATES: Final = frozenset({8_000, 16_000, 22_050, 24_000, 44_100, 48_000})
# The error messages realtime sends, each by the kind of ProviderError it is and whether asking
# again may succeed.
_REJECTED: Final = ("rejected", False)
_LIMITED: Final = ("rate_limited", True)
_FAILED: Final = ("server_error", False)
_KINDS: Final[dict[str, tuple[ProviderErrorKind, bool]]] = {
    "auth_error": _REJECTED,
    "unaccepted_terms": _REJECTED,
    "invalid_request": _REJECTED,
    "input_error": _REJECTED,
    "chunk_size_exceeded": _REJECTED,
    "quota_exceeded": _REJECTED,
    "rate_limited": _LIMITED,
    "commit_throttled": _LIMITED,
    "queue_overflow": _LIMITED,
    "resource_exhausted": _LIMITED,
    "session_time_limit_exceeded": _FAILED,
    "insufficient_audio_activity": _FAILED,
    "transcriber_error": _FAILED,
    "error": _FAILED,
}
ERRORS: Final = frozenset(_KINDS)


class RefusedError(Exception):
    """An error message from the server, named by its type alone (`ERRORS`, else `error`)."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class LiveMessage(BaseModel):
    """A server message, as far as the adapter reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    message_type: str
    text: str | None = None


def live_url(
    base_url: str, *, model: str, language: str | None, terms: tuple[str, ...], sample_rate: int
) -> str:
    """The realtime endpoint under `base_url` with a stream's query (the module's docstring)."""
    origin = base_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    query = [
        ("model_id", model),
        ("audio_format", f"pcm_{sample_rate}"),
        ("commit_strategy", "manual"),
        *([("language_code", language)] if language else []),
        ("include_language_detection", "true"),
        *(("keyterms", term) for term in terms),
    ]
    return f"{origin}{REALTIME_PATH}?{urlencode(query)}"


def audio_message(pcm16: bytes, rate: int, *, commit: bool = False) -> str:
    """One `input_audio_chunk` of `pcm16` at `rate`; with `commit`, a commit."""
    return json.dumps(
        {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(pcm16).decode("ascii"),
            "commit": commit,
            "sample_rate": rate,
        }
    )


def read_message(raw: str | bytes) -> LiveMessage:
    """One server message; AnswerError for one the adapter cannot read."""
    if isinstance(raw, bytes):
        raise AnswerError("binary_message")
    try:
        return LiveMessage.model_validate_json(raw)
    except ValidationError:
        raise AnswerError("unreadable_message") from None


def check_message(message: LiveMessage) -> None:
    """Raise `RefusedError` for an error message (its type in `ERRORS`, or ending in
    `error`)."""
    kind = message.message_type
    if kind in ERRORS or kind.endswith("error"):
        raise RefusedError(kind if kind in ERRORS else "error")


def live_failure(error: Exception) -> ProviderError:
    """The ProviderError for one failure of a stream: an error message by its kind
    (`_KINDS`), anything else as adapters/provider_socket.py's `socket_failure` maps it."""
    if isinstance(error, RefusedError):
        kind, retryable = _KINDS[error.kind]
        details: dict[str, JsonValue] = {"provider": NAME, "error": error.kind}
        return ProviderError(kind, retryable, details=details)
    return socket_failure(NAME, error)


def stream_error(
    reason: str, *, kind: ProviderErrorKind = "connection_lost", retryable: bool = True
) -> ProviderError:
    """A stream's own failure, named by `reason` (`closed`, `send_backlog`, ...)."""
    details: dict[str, JsonValue] = {"provider": NAME, "error": reason}
    return ProviderError(kind, retryable, details=details)
