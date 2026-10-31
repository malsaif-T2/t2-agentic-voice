"""What the application is running with: a typed summary of its settings, without secrets.

It takes core's Settings and returns a typed model; the health route the api layer serves
decides how to show it.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ole5_voice.core.config import Environment, LogLevel, Settings
from ole5_voice.core.errors import ConfigurationError
from ole5_voice.core.logging import get_logger

log = get_logger(__name__)


class Status(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: Environment
    log_level: LogLevel
    var_dir: Path


def status(settings: Settings) -> Status:
    """The running configuration. Production never runs with DEBUG logs, which may be verbose
    enough to carry data that should not be kept."""
    if settings.env == "prod" and settings.log_level == "DEBUG":
        raise ConfigurationError("DEBUG logging is not allowed in production.")
    log.info("status_read", env=settings.env)
    return Status(env=settings.env, log_level=settings.log_level, var_dir=settings.var_dir)
