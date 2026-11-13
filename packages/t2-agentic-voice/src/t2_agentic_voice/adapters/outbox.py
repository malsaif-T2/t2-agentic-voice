"""The outbox on SQLite (domain/ports/outbox.py), kept under `storage.var_dir` in its own file,
opened as the used-token store's is (adapters/sqlite_files.py). `INSERT OR IGNORE` on the request
ID is what makes a write never go twice, and a row is durable before `add` returns.

**How.** The file is the one `open` is given, its folder made when missing; the caller of
`open` puts it under `storage.var_dir`. Every statement commits on its own (autocommit) with
`synchronous` FULL, so a row is on disk before `add` or `mark` returns. The SQLite work runs in
a worker thread (`asyncio.to_thread`), so a commit never stalls the event loop that paces every
call's audio; one connection serves every thread, its lock held for each statement. Times are
kept as whole microseconds since the epoch, read back in UTC (sqlite_files.py's `micros` and
`instant`); rows come oldest first, by
`created_at`, then the order they were added. A row read back is parsed into an `OutboxEntry`
(a boundary). `mark` refuses a request ID the file does not hold (LookupError, naming no value),
and `count` a naive `since`; `count` leaves out the rows the caps never count (`NOT_WRITTEN`).
A row holds call content, so nothing here logs one (invariant 8).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from t2_agentic_voice.adapters.sqlite_files import connect, instant, micros, utc_now
from t2_agentic_voice.domain.ports.outbox import (
    NO_ROW,
    NOT_WRITTEN,
    OutboxEntry,
    OutboxState,
    aware_since,
)

_COLUMNS = (
    "request_id",
    "call_id",
    "subject",
    "action",
    "draft_json",
    "state",
    "note",
    "result_json",
    "created_at",
    "updated_at",
)
_SCHEMA = (
    "PRAGMA synchronous = FULL",
    "CREATE TABLE IF NOT EXISTS outbox ("
    "request_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, subject TEXT NOT NULL, "
    "action TEXT NOT NULL, draft_json TEXT NOT NULL, state TEXT NOT NULL, note TEXT, "
    "result_json TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS outbox_by_caller ON outbox (subject, action, created_at)",
    "CREATE INDEX IF NOT EXISTS outbox_by_state ON outbox (state)",
)
_ADD = (
    f"INSERT OR IGNORE INTO outbox ({', '.join(_COLUMNS)}) "  # noqa: S608 - fixed column names
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)
_MARK = (
    "UPDATE outbox SET state = ?, note = ?, result_json = COALESCE(?, result_json), "
    "updated_at = ? WHERE request_id = ?"
)
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM outbox"  # noqa: S608 - fixed column names
_ORDER = " ORDER BY created_at, rowid"
_COUNT = (
    "SELECT COUNT(*) FROM outbox WHERE subject = ? AND action = ? "  # noqa: S608 - fixed states
    f"AND created_at >= ? AND state NOT IN ({', '.join('?' for _ in NOT_WRITTEN)})"
)


def _row(entry: OutboxEntry) -> tuple[Any, ...]:
    values = entry.model_dump()
    values["created_at"] = micros(entry.created_at)
    values["updated_at"] = micros(entry.updated_at)
    return tuple(values[name] for name in _COLUMNS)


def _entry(row: tuple[Any, ...]) -> OutboxEntry:
    """A row read back, parsed."""
    values = dict(zip(_COLUMNS, row, strict=True))
    values["created_at"] = instant(values["created_at"])
    values["updated_at"] = instant(values["updated_at"])
    return OutboxEntry.model_validate(values)


class SqliteOutbox:
    """Every write of one agent, in a SQLite file under its `var_dir` folder."""

    def __init__(self, _connection: sqlite3.Connection, _now: Callable[[], datetime]) -> None:
        """Built by `open`, which opens the connection."""
        self._connection = _connection
        self._now = _now
        self._lock = threading.Lock()

    @classmethod
    async def open(cls, path: Path, *, _now: Callable[[], datetime] = utc_now) -> Self:
        """The store kept in the file `path`, created when absent; called at the runtime's
        start. Close it with `aclose()`."""
        connection = await asyncio.to_thread(connect, path, _SCHEMA)
        return cls(connection, _now)

    def _run(self, statement: str, parameters: tuple[Any, ...]) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.execute(statement, parameters)

    def _all(self, statement: str, parameters: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        with self._lock:
            rows: list[tuple[Any, ...]] = self._connection.execute(statement, parameters).fetchall()
            return rows

    async def add(self, entry: OutboxEntry) -> bool:
        """Write `entry` (the `Outbox` port's `add`), on disk before this returns: True the
        first time, False when its request ID is held already, writing nothing."""
        cursor = await asyncio.to_thread(self._run, _ADD, _row(entry))
        return cursor.rowcount == 1

    async def mark(
        self,
        request_id: str,
        *,
        state: OutboxState,
        note: str | None = None,
        result_json: str | None = None,
    ) -> None:
        """Move the row `request_id` to `state` (the `Outbox` port's `mark`), its result kept
        when none is given."""
        parameters = (state, note, result_json, micros(self._now()), request_id)
        cursor = await asyncio.to_thread(self._run, _MARK, parameters)
        if cursor.rowcount != 1:
            raise LookupError(NO_ROW)

    async def get(self, request_id: str) -> OutboxEntry | None:
        """The row `request_id`, None when there is none."""
        rows = await asyncio.to_thread(self._all, f"{_SELECT} WHERE request_id = ?", (request_id,))
        return _entry(rows[0]) if rows else None

    async def entries(
        self,
        *,
        state: OutboxState | None = None,
        subject: str | None = None,
        action: str | None = None,
    ) -> tuple[OutboxEntry, ...]:
        """The rows that match every filter given, oldest first."""
        filters = {"state": state, "subject": subject, "action": action}
        given = {column: value for column, value in filters.items() if value is not None}
        where = " AND ".join(f"{column} = ?" for column in given)
        statement = f"{_SELECT}{' WHERE ' + where if where else ''}{_ORDER}"
        rows = await asyncio.to_thread(self._all, statement, tuple(given.values()))
        return tuple(_entry(row) for row in rows)

    async def count(self, *, subject: str, action: str, since: datetime) -> int:
        """How many writes of `action` `subject` asked for since `since` that may have reached
        the system: every row but one in `NOT_WRITTEN`, so a state that list does not name
        counts."""
        parameters = (subject, action, micros(aware_since(since)), *NOT_WRITTEN)
        rows = await asyncio.to_thread(self._all, _COUNT, parameters)
        counted: int = rows[0][0]
        return counted

    async def aclose(self) -> None:
        """Close the database connection."""
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            self._connection.close()
