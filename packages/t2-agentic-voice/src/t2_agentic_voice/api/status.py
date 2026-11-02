"""What the application is running with: a typed summary of its settings, without secrets.

It takes core's VoiceSettings and returns a typed model; the health route the api layer serves
decides how to show it.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.config import Environment, VoiceSettings
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.logs import LogLevel

log = get_logger(__name__)


class Status(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: Environment
    log_level: LogLevel
    var_dir: Path


def status(settings: VoiceSettings) -> Status:
    """The running configuration. Neither staging nor production runs with DEBUG logs, which
    may be verbose enough to carry data that should not be kept, and nothing outside dev runs
    the dev page or logs call content: the checks every load makes, made again here for
    settings copied with a change (`VoiceSettings.check_environment`)."""
    settings.check_environment()
    log.info("status_read", env=settings.env)
    return Status(
        env=settings.env, log_level=settings.logging.level, var_dir=settings.storage.var_dir
    )
