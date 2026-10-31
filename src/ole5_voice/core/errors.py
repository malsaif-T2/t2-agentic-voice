"""The application's error types.

Application code raises `AppError` subclasses, each with a stable machine-readable `code`, so a
caller (an HTTP layer, a CLI, a test) can act on the kind of failure without parsing messages.
A message must be safe to show to the end user: no internals, secrets, or other users' data.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import JsonValue


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
