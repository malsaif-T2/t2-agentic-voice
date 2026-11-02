"""T2 Agentic Voice: a library for speech-first voice agents.

This module and the facades beside it (`ports`, `groq`, `identity`, `server`, `stores`, `events`,
`languages`, `evals`, `tracing`) are the library's public API (harness.toml [package] public):
an app imports from them, never from the layers inside, and ARCH-PUBLIC fails an app that does.
The layers and their rules: ARCHITECTURE.md.
"""

import warnings

from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.api.status import Status, status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import (
    ConfigurationError,
    InvalidRequestError,
    JoinRejected,
    NotFoundError,
    ProviderError,
    T2VoiceError,
)
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import configure_logging, get_logger
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

__all__ = [
    "Caller",
    "ConfigurationError",
    "Consent",
    "InvalidRequestError",
    "JoinRejected",
    "Language",
    "NotFoundError",
    "ProviderError",
    "Providers",
    "Status",
    "T2VoiceError",
    "VoiceAgent",
    "VoiceRuntime",
    "VoiceSettings",
    "configure_logging",
    "get_logger",
    "status",
]


def __getattr__(name: str) -> type[T2VoiceError]:
    """`AppError`, the base error's old name, still works until the next minor release, with a
    DeprecationWarning (the design's 5.4; D-026)."""
    if name == "AppError":
        warnings.warn(
            "t2_agentic_voice.AppError is deprecated: use T2VoiceError",
            DeprecationWarning,
            stacklevel=2,
        )
        return T2VoiceError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
