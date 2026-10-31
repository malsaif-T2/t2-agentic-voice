"""Error types: each kind has a stable code that callers act on."""

from __future__ import annotations

from t2_agentic_voice.core.errors import (
    AppError,
    ConfigurationError,
    InvalidRequestError,
    NotFoundError,
)


def test_each_error_has_a_stable_code() -> None:
    codes = [cls.code for cls in (AppError, ConfigurationError, InvalidRequestError, NotFoundError)]
    assert codes == ["internal_error", "configuration_error", "invalid_request", "not_found"]


def test_an_error_keeps_its_message_and_a_copy_of_its_details() -> None:
    details: dict[str, object] = {"id": 7}
    error = NotFoundError("No such item.", details={"id": 7})
    assert (str(error), error.message, error.details) == ("No such item.", "No such item.", details)
    assert AppError("x").details == {}
