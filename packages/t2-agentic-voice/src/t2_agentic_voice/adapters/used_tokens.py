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
dev machine. Track C's tests of each store: a row pruned once its `expires_at` has passed, and
kept while it has not; `use` with an `expires_at` a millisecond before the store's now gives
False and records nothing, so the same ID given later with a later `expires_at` gets True; and
a token used once, then given again twice with its `expires_at`, the store's clock set a
millisecond before that instant and then a millisecond after it, the row pruned between,
gets False both times.

**How.** Each `use` prunes the rows whose `expires_at` has passed by the store's clock, then
records the ID unless it is held or its `expires_at` is not after that now, all under one lock
and, for SQLite, in one `BEGIN IMMEDIATE` transaction whose insert is ignored when the ID is
held, so its answer is True exactly once and durable before it returns. The SQLite work runs
in a worker thread (`asyncio.to_thread`), so a commit's write to disk never stalls the event
loop that paces every call's audio; one connection serves every thread, its lock held for each
statement. Times are kept as whole microseconds since the epoch, so a millisecond either side
of an instant compares exactly. The store's clock is `datetime.now(UTC)` unless a test gives
its own (`_now`).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS used_tokens "
    "(token_id TEXT PRIMARY KEY, expires_at INTEGER NOT NULL) WITHOUT ROWID",
    "CREATE INDEX IF NOT EXISTS used_tokens_expires_at ON used_tokens (expires_at)",
)
_PRUNE = "DELETE FROM used_tokens WHERE expires_at < ?"
_RECORD = "INSERT OR IGNORE INTO used_tokens (token_id, expires_at) VALUES (?, ?)"


def _utc_now() -> datetime:
    """The time now, aware, in UTC: a store's clock unless a test gives its own."""
    return datetime.now(UTC)


def _aware(expires_at: datetime) -> datetime:
    """`expires_at` when it is an aware time; a naive one is refused, since the store cannot
    tell which instant it names."""
    if expires_at.utcoffset() is None:
        raise ValueError("expires_at must be an aware time (with a time zone), as UTC is")
    return expires_at


def _micros(instant: datetime) -> int:
    """`instant` as whole microseconds since the epoch: exact, where a float timestamp is not."""
    return (instant - _EPOCH) // _MICROSECOND


def _connect(path: Path) -> sqlite3.Connection:
    """The store's database at `path`, its folder and table created when missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    try:
        for statement in _SCHEMA:
            connection.execute(statement)
    except BaseException:
        connection.close()
        raise
    return connection


class SqliteUsedTokens:
    """The used tokens of one runtime, in the SQLite file `open` was given."""

    def __init__(self, _connection: sqlite3.Connection, _now: Callable[[], datetime]) -> None:
        """Built by `open`, which opens the connection."""
        self._connection = _connection
        self._now = _now
        self._lock = threading.Lock()

    @classmethod
    async def open(cls, path: Path, *, _now: Callable[[], datetime] = _utc_now) -> SqliteUsedTokens:
        """The store in the file at `path`, created with its folder when missing; called at the
        runtime's start. Close it with `aclose()`."""
        connection = await asyncio.to_thread(_connect, path)
        return cls(connection, _now)

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used (the `UsedTokens` port's `use`): True the first time."""
        until = _micros(_aware(expires_at))
        return await asyncio.to_thread(self._use, token_id, until)

    def _use(self, token_id: str, until: int) -> bool:
        """`use`'s work, in a worker thread: prune, then record, in one transaction."""
        with self._lock:
            now = _micros(self._now())
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(_PRUNE, (now,))
                recorded = (
                    until > now
                    and self._connection.execute(_RECORD, (token_id, until)).rowcount == 1
                )
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")
            return recorded

    async def aclose(self) -> None:
        """Close the database connection."""
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            self._connection.close()


class MemoryUsedTokens:
    """The used tokens in memory, gone when the process ends."""

    def __init__(self, *, _now: Callable[[], datetime] = _utc_now) -> None:
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
