"""The call log's settings (`CallLogFields`), a mixin of the app's own settings, as the flight
data's are: each is read under `FLIGHT_VOICE_` and `settings-ref` lists it."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

__all__ = ["DEFAULT_FILE", "CallLogFields"]

# The database's file under the app's storage folder (`<storage.var_dir>/flight/`).
DEFAULT_FILE = "calls.sqlite3"


class CallLogFields(BaseSettings):
    """The call log's settings; no config of its own."""

    call_log: bool = Field(
        default=True,
        description="Whether every call is kept in the call log's database (call_log/): its "
        "setup, every event, its turns and times, its tool calls and its recording's folder.",
    )
    call_log_path: Path | None = Field(
        default=None,
        description="The call log's SQLite file; unset, calls.sqlite3 in the app's storage "
        "folder (var/flight/ by default).",
    )
