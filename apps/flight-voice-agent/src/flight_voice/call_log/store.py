"""The call log's database (`CallStore`): one SQLite file, written on one thread of its own.

The tables (`SCHEMA`, version `SCHEMA_VERSION` in `meta`):

- `calls`: one row a call: its start and end, why it ended, the agent and the setup it ran on
  (`setup`, JSON: the models, the voice, the flight data's source, the release), the consent
  version, the turns, the models' usage and the browser's connection (`report`, the library's
  whole `CallReport` as JSON), and its recording's folder under the storage folder when one was
  kept (`recording`, e.g. `recordings/<call ID>`).
- `events`: every event of every call, in order, its type, turn and time, and the whole event
  as JSON (`payload`): what was heard, each reply and how much of it played, each tool call and
  its result, each interruption, guard block, provider failure and turn's times.
- `turns`: one row a turn, from the call's report: its language, what was heard, what was said,
  whether it was dropped or stopped, and its times (time to first audio, speech-to-text, the
  model's first token, the voice's first audio, the end of turn), to query without JSON.
- `tool_calls`: one row a finished tool call: its tool, arguments, result, whether it worked,
  its milliseconds and failure.

Writes are queued (`put`) and done in order on the store's thread, so a call's path never waits
on the disk; a write that fails is logged by its kind alone (the rows hold call content:
docs/SECURITY.md, invariant 8) and the store goes on with the next. The file is opened in WAL
mode, so it can be read (a report, `sqlite3`, a notebook) while the server writes it.
"""

from __future__ import annotations

import queue
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from t2_agentic_voice import get_logger

__all__ = ["SCHEMA", "SCHEMA_VERSION", "CallStore", "Row"]

_log = get_logger(__name__)

SCHEMA_VERSION: Final = 1
SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    ended_by TEXT,
    agent TEXT,
    consent_version TEXT,
    turns INTEGER,
    recording TEXT,
    setup TEXT NOT NULL,
    report TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    turn_id INTEGER,
    at TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_call ON events (call_id, id);
CREATE TABLE IF NOT EXISTS turns (
    call_id TEXT NOT NULL,
    turn_id INTEGER NOT NULL,
    language TEXT,
    heard TEXT NOT NULL,
    said TEXT NOT NULL,
    dropped INTEGER NOT NULL,
    stopped INTEGER NOT NULL,
    ttfa_ms REAL,
    stt_ms REAL,
    llm_first_token_ms REAL,
    tts_first_audio_ms REAL,
    end_of_turn_ms REAL,
    times TEXT NOT NULL,
    PRIMARY KEY (call_id, turn_id)
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    turn_id INTEGER,
    at TEXT NOT NULL,
    tool TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    arguments TEXT NOT NULL,
    result TEXT NOT NULL,
    ok INTEGER NOT NULL,
    ms REAL NOT NULL,
    failure TEXT
);
CREATE INDEX IF NOT EXISTS tool_calls_by_call ON tool_calls (call_id, id);
"""

# One write: a statement and its values.
Row = tuple[str, Sequence[object]]
_STOP: Final = None


class CallStore:
    """The database at `path`, its tables made when missing, written on its own thread (the
    module's docstring)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as made:
            made.execute("PRAGMA journal_mode=WAL")
            made.executescript(SCHEMA)
            made.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        made.close()
        self._queue: queue.Queue[list[Row] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._write, name="call-log", daemon=True)
        self._thread.start()

    def put(self, *rows: Row) -> None:
        """Queue `rows`, written together, in one transaction, in the order given."""
        self._queue.put(list(rows))

    def close(self, timeout_s: float = 10.0) -> None:
        """Write what is queued, then stop the thread."""
        self._queue.put(_STOP)
        self._thread.join(timeout_s)

    def _write(self) -> None:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            while (rows := self._queue.get()) is not _STOP:
                try:
                    with connection:
                        for statement, values in rows:
                            connection.execute(statement, tuple(values))
                except sqlite3.Error as error:
                    _log.warning("call_log_write_failed", kind=type(error).__name__)
        finally:
            connection.close()
