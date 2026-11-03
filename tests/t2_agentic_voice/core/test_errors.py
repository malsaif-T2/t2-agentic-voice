"""Error types: each kind has a stable code that callers act on."""

from __future__ import annotations

import copy
import math
import pickle

import pytest
import t2_agentic_voice
from t2_agentic_voice.core.errors import (
    PROVIDER_ERROR_KINDS,
    ConfigurationError,
    InvalidRequestError,
    JoinRejected,
    NotFoundError,
    ProviderError,
    T2VoiceError,
)

ERRORS = (
    T2VoiceError,
    ConfigurationError,
    InvalidRequestError,
    NotFoundError,
    ProviderError,
    JoinRejected,
)


def test_each_error_has_a_stable_code() -> None:
    codes = [cls.code for cls in ERRORS]
    assert codes == [
        "internal_error",
        "configuration_error",
        "invalid_request",
        "not_found",
        "provider_error",
        "join_rejected",
    ]


def test_an_error_keeps_its_message_and_a_copy_of_its_details() -> None:
    details: dict[str, object] = {"id": 7}
    error = NotFoundError("No such item.", details={"id": 7})
    assert (str(error), error.message, error.details) == ("No such item.", "No such item.", details)
    assert T2VoiceError("x").details == {}


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
    for again in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):  # noqa: S301 - loads only bytes it dumped
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
    for again in (pickle.loads(pickle.dumps(error)), copy.copy(error), copy.deepcopy(error)):  # noqa: S301 - loads only bytes it dumped
        assert (type(again), again.message, again.details) == (
            ConfigurationError,
            error.message,
            error.details,
        )


def test_the_package_root_exports_provider_error() -> None:
    assert t2_agentic_voice.ProviderError is ProviderError
    assert "ProviderError" in t2_agentic_voice.__all__


def test_the_package_root_exports_join_rejected_on_the_base_error() -> None:
    """The design's 5.1 lists it among the root's errors; a caller catches it as any other."""
    assert t2_agentic_voice.JoinRejected is JoinRejected
    assert "JoinRejected" in t2_agentic_voice.__all__
    error = JoinRejected("This call cannot start.", details={"setting": "join.keys"})
    assert isinstance(error, T2VoiceError) and error.code == "join_rejected"
    again = pickle.loads(pickle.dumps(error))  # noqa: S301 - loads only bytes it dumped
    assert (type(again), again.message, again.details) == (
        JoinRejected,
        error.message,
        error.details,
    )


def test_the_old_name_app_error_warns_and_is_the_base_error() -> None:
    """The base error's old name works until the next minor release, with a DeprecationWarning
    (the design's 5.4; D-026); any other missing name is still an AttributeError."""
    with pytest.warns(DeprecationWarning, match="use T2VoiceError"):
        old = t2_agentic_voice.AppError
    assert old is T2VoiceError
    assert "AppError" not in t2_agentic_voice.__all__ and "T2VoiceError" in t2_agentic_voice.__all__
    with pytest.raises(AttributeError, match="no attribute 'Missing'"):
        _ = t2_agentic_voice.Missing
