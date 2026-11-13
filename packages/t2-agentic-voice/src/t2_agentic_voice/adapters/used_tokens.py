"""The used-token stores (the design's 6.5): the join tokens already used, each by its `jti`, so a
token starts one call only; `UsedTokens`. Public through the `stores` facade (provisional).

`SqliteUsedTokens` keeps them in a SQLite file under `storage.var_dir`, across restarts, and
gives exactly one of two joins that use one token at once its True, from two threads too; only
`adapters` imports `sqlite3` (`[[owners]]`). A row is kept at least until its `expires_at`, the
last instant any verifier could still accept its token (the token's `exp` plus
`MAX_CLOCK_SKEW_S`, the bound on `join.max_clock_skew_s`, as `SignedJoinTokens` passes it), and
is pruned only after that. `use` reads the store's own clock, and gives False for an
`expires_at` that is not after its now, recording nothing. One process per `var_dir` holds the
file (the runtime's lock file). `MemoryUsedTokens` keeps them in memory only, for tests and a
dev machine. Each store's tests hold: a row pruned once its `expires_at` has passed, and kept
while it has not; `use` with an `expires_at` a millisecond before the store's now gives False
and records nothing, so the same ID given later with a later `expires_at` gets True; and a
token used once, then given again twice with its `expires_at`, the store's clock set a
millisecond before that instant and then a millisecond after it, the row pruned between,
gets False both times.

**How.** Each `use` prunes the rows whose `expires_at` has passed by the store's clock, then
records the ID unless it is held or its `expires_at` is not after that now, all under one lock
and, for SQLite, in one `BEGIN IMMEDIATE` transaction whose insert is ignored when the ID is
held, so its answer is True exactly once and durable before it returns. A failure anywhere in
that transaction, its `COMMIT` included (busy while a reader holds the file), rolls it back
unless SQLite already has, and is raised: it refuses that one join, and the next one starts a
transaction of its own. The SQLite work runs in a worker thread (`asyncio.to_thread`), so a
commit's write to disk never stalls the event loop that paces every call's audio; one
connection serves every thread, its lock held for each statement. The file is opened and its
times kept as adapters/sqlite_files.py says (whole microseconds since the epoch, so a
millisecond either side of an instant compares exactly). The store's clock is
`datetime.now(UTC)` unless a test gives its own (`_now`).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from t2_agentic_voice.adapters.sqlite_files import connect, micros, utc_now

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS used_tokens "
    "(token_id TEXT PRIMARY KEY, expires_at INTEGER NOT NULL) WITHOUT ROWID",
    "CREATE INDEX IF NOT EXISTS used_tokens_expires_at ON used_tokens (expires_at)",
)
_PRUNE = "DELETE FROM used_tokens WHERE expires_at < ?"
_RECORD = "INSERT OR IGNORE INTO used_tokens (token_id, expires_at) VALUES (?, ?)"


def _aware(expires_at: datetime) -> datetime:
    """`expires_at` when it is an aware time; a naive one is refused, since the store cannot
    tell which instant it names."""
    if expires_at.utcoffset() is None:
        raise ValueError("expires_at must be an aware time (with a time zone), as UTC is")
    return expires_at


class SqliteUsedTokens:
    """The used tokens of one runtime, in the SQLite file `open` was given."""

    def __init__(self, _connection: sqlite3.Connection, _now: Callable[[], datetime]) -> None:
        """Built by `open`, which opens the connection."""
        self._connection = _connection
        self._now = _now
        self._lock = threading.Lock()

    @classmethod
    async def open(cls, path: Path, *, _now: Callable[[], datetime] = utc_now) -> SqliteUsedTokens:
        """The store in the file at `path`, created with its folder when missing; called at the
        runtime's start. Close it with `aclose()`."""
        connection = await asyncio.to_thread(connect, path, _SCHEMA)
        return cls(connection, _now)

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used (the `UsedTokens` port's `use`): True the first time."""
        until = micros(_aware(expires_at))
        return await asyncio.to_thread(self._use, token_id, until)

    def _use(self, token_id: str, until: int) -> bool:
        """`use`'s work, in a worker thread: prune, then record, in one transaction."""
        with self._lock:
            now = micros(self._now())
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(_PRUNE, (now,))
                recorded = (
                    until > now
                    and self._connection.execute(_RECORD, (token_id, until)).rowcount == 1
                )
                self._connection.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:  # none when SQLite rolled it back itself
                    self._connection.execute("ROLLBACK")
                raise
            return recorded

    async def aclose(self) -> None:
        """Close the database connection."""
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            self._connection.close()


class MemoryUsedTokens:
    """The used tokens in memory, gone when the process ends."""

    def __init__(self, *, _now: Callable[[], datetime] = utc_now) -> None:
        self._now = _now
        self._used: dict[str, datetime] = {}
        self._lock = threading.Lock()

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used (the `UsedTokens` port's `use`): True the first time."""
        _aware(expires_at)
        with self._lock:
            now = self._now()
            self._used = {held: until for held, until in self._used.items() if until >= now}
            if expires_at <= now or token_id in self._used:
                return False
            self._used[token_id] = expires_at
            return True

    async def aclose(self) -> None:
        """Nothing to close."""
