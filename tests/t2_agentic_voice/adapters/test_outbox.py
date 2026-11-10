"""The outbox stores (domain/ports/outbox.py; docs/SECURITY.md, invariant 6), SQLite's
(adapters/outbox.py) and the one in memory (actions/memory_outbox.py), held to the same port: a
request ID held once, `INSERT OR IGNORE`, so a write never goes twice; a row moved on, its
result kept; rows by filter, oldest first; a count since an aware time of the writes that may
have reached the system. SQLite's own: a row on disk before `add` returns, read back by a later
open of the file, its folder made."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from t2_agentic_voice.actions.memory_outbox import NO_ROW, MemoryOutbox
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.domain.ports.outbox import Outbox, OutboxEntry, OutboxState

AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
LATER = AT + timedelta(minutes=5)


class Clock:
    """A store's clock, set by the test."""

    def __init__(self) -> None:
        self.now = LATER

    def __call__(self) -> datetime:
        return self.now


def _entry(request_id: str = "r-1", **changes: Any) -> OutboxEntry:
    values: dict[str, Any] = {
        "request_id": request_id,
        "call_id": "call-1",
        "subject": "made-up-subject",
        "action": "open_request",
        "draft_json": '{"summary": "made up"}',
        "created_at": AT,
        "updated_at": AT,
    }
    return OutboxEntry.model_validate(values | changes)


Body = Callable[[Outbox, Clock], Coroutine[Any, Any, None]]


@pytest.fixture(params=["memory", "sqlite"])
def within_store(request: pytest.FixtureRequest, tmp_path: Path) -> Callable[[Body], None]:
    """Run a test's body against each store, closed after."""

    def run(body: Body) -> None:
        async def held() -> None:
            clock = Clock()
            store: Outbox
            if request.param == "memory":
                store = MemoryOutbox(_now=clock)
            else:
                store = await SqliteOutbox.open(tmp_path / "outbox.sqlite3", _now=clock)
            try:
                await body(store, clock)
            finally:
                await store.aclose()

        asyncio.run(held())

    return run


def test_a_request_id_is_held_once_and_a_second_add_writes_nothing(
    within_store: Callable[[Body], None],
) -> None:
    async def body(store: Outbox, clock: Clock) -> None:
        assert await store.add(_entry()) is True
        assert await store.add(_entry(draft_json='{"summary": "other"}', subject="x")) is False
        assert await store.get("r-1") == _entry()
        assert await store.get("r-2") is None

    within_store(body)


def test_a_row_moves_on_with_its_note_and_keeps_its_result(
    within_store: Callable[[Body], None],
) -> None:
    async def body(store: Outbox, clock: Clock) -> None:
        await store.add(_entry())
        await store.mark("r-1", state="done", note="looked_up", result_json='{"number": "1"}')
        done = await store.get("r-1")
        assert done is not None and (done.state, done.note) == ("done", "looked_up")
        assert done.result_json == '{"number": "1"}' and done.updated_at == LATER
        assert done.created_at == AT
        clock.now = LATER + timedelta(seconds=1)
        await store.mark("r-1", state="flagged")
        flagged = await store.get("r-1")
        assert flagged is not None and (flagged.state, flagged.note) == ("flagged", None)
        assert flagged.result_json == '{"number": "1"}'

    within_store(body)


def test_marking_a_row_the_store_does_not_hold_names_no_value(
    within_store: Callable[[Body], None],
) -> None:
    async def body(store: Outbox, clock: Clock) -> None:
        with pytest.raises(LookupError) as raised:
            await store.mark("made-up-request-4521", state="done")
        assert str(raised.value) == NO_ROW and "4521" not in str(raised.value)

    within_store(body)


def test_rows_come_by_filter_oldest_first(within_store: Callable[[Body], None]) -> None:
    async def body(store: Outbox, clock: Clock) -> None:
        await store.add(_entry("r-late", created_at=AT + timedelta(seconds=9)))
        await store.add(_entry("r-early", subject="someone-else"))
        await store.add(_entry("r-tie", action="add_note"))
        await store.mark("r-tie", state="rejected")
        every = [row.request_id for row in await store.entries()]
        assert every == ["r-early", "r-tie", "r-late"]
        mine = await store.entries(subject="made-up-subject")
        assert [row.request_id for row in mine] == ["r-tie", "r-late"]
        assert [r.request_id for r in await store.entries(state="rejected")] == ["r-tie"]
        both = await store.entries(subject="made-up-subject", action="open_request")
        assert [row.request_id for row in both] == ["r-late"]

    within_store(body)


def test_a_count_reads_a_callers_rows_of_an_action_since_an_aware_time(
    within_store: Callable[[Body], None],
) -> None:
    async def body(store: Outbox, clock: Clock) -> None:
        await store.add(_entry("r-1"))
        await store.add(_entry("r-2", created_at=AT + timedelta(hours=1)))
        await store.add(_entry("r-3", subject="someone-else"))
        await store.mark("r-2", state="flagged")  # it may have reached the system: counted
        count = store.count
        assert await count(subject="made-up-subject", action="open_request", since=AT) == 2
        later = AT + timedelta(minutes=1)
        assert await count(subject="made-up-subject", action="open_request", since=later) == 1
        riyadh = timezone(timedelta(hours=3))
        same = AT.astimezone(riyadh)
        assert await count(subject="made-up-subject", action="open_request", since=same) == 2
        assert await count(subject="made-up-subject", action="add_note", since=AT) == 0
        with pytest.raises(ValueError, match="aware"):
            await count(
                subject="made-up-subject", action="open_request", since=AT.replace(tzinfo=None)
            )

    within_store(body)


def test_a_count_leaves_out_a_write_rejected_or_not_sent(
    within_store: Callable[[Body], None],
) -> None:
    """The caps read the count, and count only a write that may have reached the system: one
    `sending`, `done` or `flagged`, never one the backend `rejected` or one `not_sent`."""

    async def body(store: Outbox, clock: Clock) -> None:
        states: tuple[OutboxState, ...] = ("done", "flagged", "rejected", "not_sent")
        await store.add(_entry("r-sending"))
        for state in states:
            await store.add(_entry(f"r-{state}"))
            await store.mark(f"r-{state}", state=state)
        counted = await store.count(subject="made-up-subject", action="open_request", since=AT)
        assert counted == 3

    within_store(body)


def test_a_sqlite_row_is_on_disk_before_add_returns_and_read_back_by_a_later_open(
    tmp_path: Path,
) -> None:
    path = tmp_path / "store" / "agent" / "outbox.sqlite3"

    async def first() -> None:
        store = await SqliteOutbox.open(path)
        await store.add(_entry(created_at=AT.astimezone(timezone(timedelta(hours=3)))))
        await store.aclose()

    async def second() -> tuple[OutboxEntry | None, bool]:
        store = await SqliteOutbox.open(path)
        try:
            return await store.get("r-1"), await store.add(_entry())
        finally:
            await store.aclose()

    asyncio.run(first())
    assert path.is_file()
    row, added_again = asyncio.run(second())
    assert row is not None and row.created_at == AT and row.created_at.tzinfo == UTC
    assert row.draft_json == '{"summary": "made up"}' and row.state == "sending"
    assert added_again is False
