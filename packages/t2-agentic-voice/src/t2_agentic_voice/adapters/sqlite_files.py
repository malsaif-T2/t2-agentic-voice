"""What the SQLite stores share (adapters/used_tokens.py, adapters/outbox.py): the file opened
with its schema, and an instant kept as whole microseconds since the epoch.

`connect` makes the file's folder when missing and opens one connection in autocommit
(`isolation_level=None`, so a store begins its own transactions), usable from every worker
thread the store runs on (each store holds its own lock for each statement), then runs the
store's schema; a schema that fails (a file that is no database) closes the connection before
the error is raised, so no handle keeps the file. Times are whole microseconds, so a
millisecond either side of an instant compares exactly, where a float timestamp does not, and
are read back aware, in UTC.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


def utc_now() -> datetime:
    """The time now, aware, in UTC: a store's clock unless a test gives its own."""
    return datetime.now(UTC)


def micros(instant: datetime) -> int:
    """`instant` as whole microseconds since the epoch: exact, where a float timestamp is not."""
    return (instant - _EPOCH) // _MICROSECOND


def instant(micros: int) -> datetime:
    """The instant `micros` whole microseconds after the epoch, aware, in UTC."""
    return _EPOCH + micros * _MICROSECOND


def connect(path: Path, schema: Sequence[str]) -> sqlite3.Connection:
    """The store's database at `path`, its folder made and `schema` run (the module's
    docstring)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    try:
        for statement in schema:
            connection.execute(statement)
    except BaseException:
        connection.close()
        raise
    return connection
