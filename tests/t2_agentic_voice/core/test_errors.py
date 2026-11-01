"""Error types: each kind has a stable code that callers act on."""

from __future__ import annotations

import copy
import math
import pickle

import pytest
import t2_agentic_voice
from t2_agentic_voice.core.errors import (
    PROVIDER_ERROR_KINDS,
    AppError,
    ConfigurationError,
    InvalidRequestError,
    NotFoundError,
    ProviderError,
)

ERRORS = (AppError, ConfigurationError, InvalidRequestError, NotFoundError, ProviderError)


def test_each_error_has_a_stable_code() -> None:
    codes = [cls.code for cls in ERRORS]
    assert codes == [
        "internal_error",
        "configuration_error",
        "invalid_request",
        "not_found",
        "provider_error",
    ]


def test_an_error_keeps_its_message_and_a_copy_of_its_details() -> None:
    details: dict[str, object] = {"id": 7}
    error = NotFoundError("No such item.", details={"id": 7})
    assert (str(error), error.message, error.details) == ("No such item.", "No such item.", details)
    assert AppError("x").details == {}


def test_a_provider_error_has_a_kind_from_a_closed_list() -> None:
    assert PROVIDER_ERROR_KINDS == (
        "rate_limited",
        "timeout",
        "connection_lost",
        "server_error",
        "rejected",
    )
    error = ProviderError("rate_limited", True, 20.0, details={"status": 429})
    assert (error.kind, error.retryable, error.retry_after_s) == ("rate_limited", True, 20.0)
    assert (error.code, error.details) == ("provider_error", {"status": 429})
    messages = {ProviderError(kind, kind != "rejected").message for kind in PROVIDER_ERROR_KINDS}
    assert len(messages) == len(PROVIDER_ERROR_KINDS)


@pytest.mark.parametrize(
    ("kind", "retryable", "retry_after_s"),
    [
        ("quota", True, None),  # not a kind
        ("rejected", True, None),  # an authentication or request error is never retried
        ("rejected", False, 5.0),  # a wait only on a retryable error
        ("rate_limited", True, -1.0),
        ("rate_limited", True, math.inf),
        ("timeout", True, math.nan),
    ],
)
def test_a_provider_error_refuses_an_impossible_shape(
    kind: str, retryable: bool, retry_after_s: float | None
) -> None:
    with pytest.raises(ValueError, match=r"kind|retryable|retry_after_s"):
        ProviderError(kind, retryable, retry_after_s)  # type: ignore[arg-type]


@pytest.mark.parametrize("retry_after_s", [2.5, None])
def test_a_provider_error_pickles_and_copies_whole(retry_after_s: float | None) -> None:
    error = ProviderError("rate_limited", True, retry_after_s, details={"status": 429})
    error.add_note("attempt 3")
    for again in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):  # noqa: S301
        assert type(again) is ProviderError
        assert (again.kind, again.retryable, again.retry_after_s) == (
            "rate_limited",
            True,
            retry_after_s,
        )
        assert (again.message, again.args, again.code) == (error.message, error.args, error.code)
        assert (again.details, again.__notes__) == ({"status": 429}, ["attempt 3"])


def test_the_other_errors_pickle_and_copy_too() -> None:
    error = ConfigurationError("Set T2V_GROQ__API_KEY.", details={"setting": "T2V_GROQ__API_KEY"})
    for again in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):  # noqa: S301
        assert (type(again), again.message, again.details) == (
            ConfigurationError,
            error.message,
            error.details,
        )


def test_the_package_root_exports_provider_error() -> None:
    assert t2_agentic_voice.ProviderError is ProviderError
    assert "ProviderError" in t2_agentic_voice.__all__
