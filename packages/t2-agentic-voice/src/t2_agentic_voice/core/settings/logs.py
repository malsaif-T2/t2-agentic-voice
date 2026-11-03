"""The `logging` group: the library's log level and format, and what its lines may hold. The
module is not called `logging.py`, so it is never mistaken for the standard library's."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]
# What becomes of Pipecat's own log lines: off for now (plan 003, Q19).
PipecatLogs = Literal["off"]


class LoggingSettings(Group):
    """Logging: the level and format of the library's lines, and what they may hold."""

    level: LogLevel = Field(
        default="INFO",
        description="DEBUG, INFO, WARNING or ERROR; staging and prod refuse DEBUG.",
    )
    format: LogFormat = Field(
        default="console",
        description="console (human-readable) or json (machine-queryable).",
    )
    content: bool = Field(
        default=False,
        description=(
            "Whether log lines may hold what was said in a call; refused outside dev "
            "(docs/SECURITY.md, invariant 8)."
        ),
    )
    pipecat: PipecatLogs = Field(
        default="off",
        description="What becomes of the voice framework's own log lines: off, the only value.",
    )
