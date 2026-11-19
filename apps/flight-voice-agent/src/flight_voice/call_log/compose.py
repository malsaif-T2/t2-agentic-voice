"""The server's call log (`call_log_of`), from the settings: none when `call_log` is off, else the
database at `call_log_path` (calls.sqlite3 in the app's storage folder by default), with the
setup the server's agent runs on and the release it runs from."""

from __future__ import annotations

from pathlib import Path

from t2_agentic_voice import VoiceAgent, VoiceSettings

from flight_voice.call_log.log import CallLog
from flight_voice.call_log.settings import DEFAULT_FILE, CallLogFields
from flight_voice.call_log.setup import call_setup, release
from flight_voice.call_log.store import CallStore
from flight_voice.flight_data.settings import FlightDataFields

__all__ = ["call_log_of", "log_path"]


def log_path(app: CallLogFields, voice: VoiceSettings) -> Path:
    """The call log's database file (the module's docstring)."""
    return app.call_log_path or voice.storage.var_dir / DEFAULT_FILE


def call_log_of(
    app: CallLogFields, flights: FlightDataFields, voice: VoiceSettings, agent: VoiceAgent
) -> CallLog | None:
    """The call log of a server of `agent` (the module's docstring)."""
    if not app.call_log:
        return None
    setup = call_setup(agent, voice, flights, release())
    return CallLog(CallStore(log_path(app, voice)), setup, voice.storage.var_dir)
