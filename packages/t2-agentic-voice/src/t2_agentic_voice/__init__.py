"""T2 Agentic Voice: a library for speech-first voice agents.

This module is the library's public API (harness.toml [package] public): an app imports from
here, never from the layers inside, and ARCH-PUBLIC fails an app that does. The layers and their
rules: ARCHITECTURE.md.
"""

from t2_agentic_voice.api.status import Status, status
from t2_agentic_voice.core.config import Settings, get_settings
from t2_agentic_voice.core.errors import (
    AppError,
    ConfigurationError,
    InvalidRequestError,
    NotFoundError,
    ProviderError,
)
from t2_agentic_voice.core.logging import configure_logging, get_logger

__all__ = [
    "AppError",
    "ConfigurationError",
    "InvalidRequestError",
    "NotFoundError",
    "ProviderError",
    "Settings",
    "Status",
    "configure_logging",
    "get_logger",
    "get_settings",
    "status",
]
