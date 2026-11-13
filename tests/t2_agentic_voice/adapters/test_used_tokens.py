"""The used-token stores (adapters/used_tokens.py): each token's `jti` used once, kept until its
last instant and pruned after it, by the store's own clock; the SQLite store under two threads
and after a restart."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens, SqliteUsedTokens
from t2_agentic_voice.domain.ports.identity import UsedTokens

EXPIRES = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
MS = timedelta(milliseconds=1)


class Clock:
    """A store's clock that moves only when a test sets it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


type Store = SqliteUsedTokens | MemoryUsedTokens
type Opener = Callable[[Path, Clock], Awaitable[Store]]


async def _sqlite(folder: Path, clock: Clock) -> Store:
    return await SqliteUsedTokens.open(folder / "var" / "used_tokens.db", _now=clock)


async def _memory(folder: Path, clock: Clock) -> Store:
    return MemoryUsedTokens(_now=clock)


STORES: dict[str, Opener] = {"sqlite": _sqlite, "memory": _memory}


def _held(store: Store) -> set[str]:
    """The IDs the store holds now, read past its port."""
    if isinstance(store, MemoryUsedTokens):
        return set(store._used)
    rows = store._connection.execute("SELECT token_id FROM used_tokens").fetchall()
    return {token_id for (token_id,) in rows}


def _run[T](
    opener: Opener, folder: Path, clock: Clock, steps: Callable[[Store], Awaitable[T]]
) -> T:
    """`steps` run on a store `opener` opens, which is closed after."""

    async def run() -> T:
        store = await opener(folder, clock)
        try:
            return await steps(store)
        finally:
            await store.aclose()

    return asyncio.run(run())


def test_the_stores_meet_the_port(tmp_path: Path) -> None:
    async def both() -> None:
        stores: list[UsedTokens] = [  # mypy checks the port's shape
            await SqliteUsedTokens.open(tmp_path / "used.db"),
            MemoryUsedTokens(),
        ]
        for store in stores:
            assert await store.use("made-up", expires_at=datetime.now(UTC) + timedelta(minutes=1))
            await store.aclose()

    asyncio.run(both())


@pytest.mark.parametrize("opener", STORES.values(), ids=STORES.keys())
def test_a_row_is_kept_until_its_expires_at_and_pruned_once_it_has_passed(
    opener: Opener, tmp_path: Path
) -> None:
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def steps(store: Store) -> None:
        assert await store.use("a", expires_at=EXPIRES)
        assert await store.use("b", expires_at=EXPIRES + timedelta(seconds=30))
        clock.now = EXPIRES  # "a"'s last instant: still kept
        assert await store.use("c", expires_at=EXPIRES + timedelta(minutes=5))
        assert _held(store) == {"a", "b", "c"}
        clock.now = EXPIRES + MS  # "a"'s has passed
        assert await store.use("d", expires_at=EXPIRES + timedelta(minutes=5))
        assert _held(store) == {"b", "c", "d"}
        assert not await store.use("b", expires_at=EXPIRES + timedelta(seconds=30))

    _run(opener, tmp_path, clock, steps)


@pytest.mark.parametrize("opener", STORES.values(), ids=STORES.keys())
def test_a_use_whose_last_instant_has_passed_records_nothing(
    opener: Opener, tmp_path: Path
) -> None:
    clock = Clock(EXPIRES + MS)

    async def steps(store: Store) -> None:
        assert not await store.use("late", expires_at=EXPIRES)
        assert _held(store) == set()
        clock.now = EXPIRES  # an expires_at equal to now is not after it
        assert not await store.use("late", expires_at=EXPIRES)
        assert await store.use("late", expires_at=EXPIRES + timedelta(seconds=60))
        assert _held(store) == {"late"}

    _run(opener, tmp_path, clock, steps)


@pytest.mark.parametrize("opener", STORES.values(), ids=STORES.keys())
def test_a_replay_either_side_of_the_last_instant_is_refused(
    opener: Opener, tmp_path: Path
) -> None:
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def steps(store: Store) -> None:
        assert await store.use("once", expires_at=EXPIRES)
        clock.now = EXPIRES - MS
        assert not await store.use("once", expires_at=EXPIRES)
        assert _held(store) == {"once"}
        clock.now = EXPIRES + MS
        assert not await store.use("once", expires_at=EXPIRES)
        assert _held(store) == set()  # pruned between

    _run(opener, tmp_path, clock, steps)


@pytest.mark.parametrize("opener", STORES.values(), ids=STORES.keys())
def test_two_joins_of_one_token_at_once_get_one_true(opener: Opener, tmp_path: Path) -> None:
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def steps(store: Store) -> list[bool]:
        return list(
            await asyncio.gather(*(store.use("twice", expires_at=EXPIRES) for _ in range(8)))
        )

    assert sorted(_run(opener, tmp_path, clock, steps)) == [False] * 7 + [True]


@pytest.mark.parametrize("stores", [1, 2], ids=["one store", "two stores on one file"])
def test_two_threads_using_each_token_at_once_get_one_true(stores: int, tmp_path: Path) -> None:
    path = tmp_path / "used.db"
    opened = [asyncio.run(SqliteUsedTokens.open(path)) for _ in range(stores)]
    later = datetime.now(UTC) + timedelta(minutes=5)
    tokens = [f"jti-{n}" for n in range(40)]
    barrier = threading.Barrier(2)
    results: dict[str, list[bool]] = {token: [] for token in tokens}
    lock = threading.Lock()

    def joins(store: SqliteUsedTokens) -> None:
        async def run() -> None:
            for token in tokens:
                barrier.wait(timeout=10)
                used = await store.use(token, expires_at=later)
                with lock:
                    results[token].append(used)

        asyncio.run(run())

    threads = [threading.Thread(target=joins, args=(opened[n % stores],)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for store in opened:
        asyncio.run(store.aclose())
    assert all(sorted(used) == [False, True] for used in results.values())


def test_a_token_used_before_a_restart_is_refused_after_it(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "folder" / "used.db"
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def restart() -> tuple[bool, bool, bool]:
        first = await SqliteUsedTokens.open(path, _now=clock)
        used = await first.use("kept", expires_at=EXPIRES)
        await first.aclose()
        second = await SqliteUsedTokens.open(path, _now=clock)
        try:
            again = await second.use("kept", expires_at=EXPIRES)
            other = await second.use("other", expires_at=EXPIRES)
        finally:
            await second.aclose()
        return used, again, other

    assert asyncio.run(restart()) == (True, False, True)


def test_a_naive_expires_at_is_refused(tmp_path: Path) -> None:
    naive = EXPIRES.replace(tzinfo=None)

    async def steps(store: Store) -> None:
        with pytest.raises(ValueError, match="aware time"):
            await store.use("naive", expires_at=naive)
        assert _held(store) == set()

    for opener in STORES.values():
        _run(opener, tmp_path, Clock(EXPIRES - timedelta(seconds=90)), steps)


def test_a_failed_use_leaves_no_transaction_open(tmp_path: Path) -> None:
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def steps(store: Store) -> None:
        with pytest.raises(sqlite3.ProgrammingError, match="binding parameter"):
            await store.use(["not", "an", "id"], expires_at=EXPIRES)  # type: ignore[arg-type]
        assert await store.use("next", expires_at=EXPIRES)

    _run(_sqlite, tmp_path, clock, steps)


def test_a_failed_commit_refuses_that_join_alone(tmp_path: Path) -> None:
    """A reader holding the file (an operator's shell, a backup) makes `COMMIT` fail as busy,
    which leaves SQLite's transaction open: the store rolls it back, so that one join is
    refused, nothing of it kept, and the next join is taken."""
    path = tmp_path / "used.db"
    clock = Clock(EXPIRES - timedelta(seconds=90))

    async def steps() -> tuple[bool, bool]:
        store = await SqliteUsedTokens.open(path, _now=clock)
        store._connection.execute("PRAGMA busy_timeout = 0")  # busy at once, not in 5 s
        reader = sqlite3.connect(path, isolation_level=None)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT COUNT(*) FROM used_tokens").fetchall()  # its shared lock
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                await store.use("held", expires_at=EXPIRES)
            reader.execute("COMMIT")
            return (
                await store.use("next", expires_at=EXPIRES),
                await store.use("held", expires_at=EXPIRES),
            )
        finally:
            reader.close()
            await store.aclose()

    assert asyncio.run(steps()) == (True, True)


def test_a_file_that_is_no_database_is_refused_and_closed(tmp_path: Path) -> None:
    path = tmp_path / "used.db"
    path.write_bytes(b"not a database, made up for the test " * 64)
    with pytest.raises(sqlite3.DatabaseError, match="not a database"):
        asyncio.run(SqliteUsedTokens.open(path))
    path.unlink()  # Windows refuses this while a connection holds the file
