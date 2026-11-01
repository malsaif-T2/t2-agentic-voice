"""The application's error types.

Application code raises `AppError` subclasses, each with a stable machine-readable `code`, so a
caller (an HTTP layer, a CLI, a test) can act on the kind of failure without parsing messages.
A message must be safe to show to the end user: no internals, secrets, or other users' data.
"""

from __future__ import annotations

import math
from typing import ClassVar, Literal, get_args

from pydantic import JsonValue

# How a provider failed a request: a closed list, so a caller can act on each kind.
ProviderErrorKind = Literal[
    "rate_limited", "timeout", "connection_lost", "server_error", "rejected"
]
PROVIDER_ERROR_KINDS: tuple[ProviderErrorKind, ...] = get_args(ProviderErrorKind)
_PROVIDER_MESSAGES: dict[ProviderErrorKind, str] = {
    "rate_limited": "The provider is limiting requests for now.",
    "timeout": "The provider did not answer in time.",
    "connection_lost": "The connection to the provider was lost.",
    "server_error": "The provider failed to answer.",
    "rejected": "The provider refused the request.",
}


class AppError(Exception):
    code: ClassVar[str] = "internal_error"

    def __init__(self, message: str, *, details: dict[str, JsonValue] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, JsonValue] = dict(details or {})


class ConfigurationError(AppError):
    """The application is configured in a way it cannot run with."""

    code = "configuration_error"


class InvalidRequestError(AppError):
    """A well-formed request with invalid content."""

    code = "invalid_request"


class NotFoundError(AppError):
    """A lookup for something that does not exist."""

    code = "not_found"


class ProviderError(AppError):
    """An outside service (speech-to-text, the model, text-to-speech) failed a request.

    `kind` says how, from a closed list: `rate_limited`, `timeout`, `connection_lost`,
    `server_error`, or `rejected` (an authentication or request error). `retryable` says whether
    asking again may succeed, and is never true for `rejected`. `retry_after_s` is how long the
    provider asked to wait, when it said, and only on a retryable error. Every port raises this
    on a provider's failure (the design's 6.1). The message is fixed per kind and never holds the
    provider's own text, which may echo the request.
    """

    code = "provider_error"

    def __init__(
        self,
        kind: ProviderErrorKind,
        retryable: bool,
        retry_after_s: float | None = None,
        *,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        if kind not in PROVIDER_ERROR_KINDS:
            raise ValueError(f"unknown provider error kind {kind!r}; one of {PROVIDER_ERROR_KINDS}")
        if kind == "rejected" and retryable:
            raise ValueError("a rejected request is never retryable")
        if retry_after_s is not None and not (retryable and math.isfinite(retry_after_s)):
            raise ValueError("retry_after_s is a finite wait, given only on a retryable error")
        if retry_after_s is not None and retry_after_s < 0:
            raise ValueError("retry_after_s is a wait, never negative")
        super().__init__(_PROVIDER_MESSAGES[kind], details=details)
        self.kind: ProviderErrorKind = kind
        self.retryable = retryable
        self.retry_after_s = retry_after_s
