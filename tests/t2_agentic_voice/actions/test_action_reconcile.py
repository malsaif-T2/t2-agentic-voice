"""The action runner's `reconcile` (actions/action_job.py; docs/SECURITY.md, invariant 6): at a
start, each row an earlier process left `sending` is looked up by its request ID and marked
`done` when found, else `flagged` for a person, and never sent again; a row whose write is under
way in this process is left to its job. The earlier process here is a real one's end: its loop
stopped while the write ran, on the SQLite outbox, which a later start opens again."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.domain.ports.outbox import OutboxEntry

from tests.t2_agentic_voice.actions.action_support import (
    CALL_ID,
    CALLER,
    ISSUED,
    Backend,
    RequestOpened,
    Rig,
    an_action,
    until,
)
from tests.t2_agentic_voice.fakes import FakeClock


def _left_sending(path: Path) -> str:
    """A process that confirmed a write and stopped while it ran: its row left `sending`."""

    async def first() -> str:
        store = await SqliteOutbox.open(path)
        rig = Rig("hang", outbox=store)
        job = asyncio.ensure_future(rig.confirmed_run())
        await until(lambda: bool(rig.backend.writes))
        [(ctx, _)] = rig.backend.writes
        await store.aclose()
        job.cancel()
        return ctx.request_id

    return asyncio.run(first())


@pytest.mark.parametrize(
    ("held", "lookup", "state", "note"),
    [
        (True, True, "done", "looked_up"),
        (False, True, "flagged", "left, not_found"),
        (True, False, "flagged", "left, no_lookup"),
    ],
    ids=["found", "not found", "no lookup"],
)
def test_a_row_left_sending_is_looked_up_or_flagged_at_the_next_start_never_sent_again(
    tmp_path: Path, held: bool, lookup: bool, state: str, note: str
) -> None:
    path = tmp_path / "agent" / "outbox.sqlite3"
    request_id = _left_sending(path)

    async def second() -> tuple[int, int, OutboxEntry | None, Backend]:
        store = await SqliteOutbox.open(path)
        try:
            clock = FakeClock()
            backend = Backend("answer", outbox=store, clock=clock)
            if held:  # the system did the write before the earlier process stopped
                backend.held[request_id] = RequestOpened(number=ISSUED)
            runner = ActionRunner([an_action(backend, lookup=lookup)], outbox=store)
            handled = await runner.reconcile(clock=clock)
            again = await runner.reconcile(clock=clock)
            return handled, again, await store.get(request_id), backend
        finally:
            await store.aclose()

    handled, again, row, backend = asyncio.run(second())
    assert (handled, again) == (1, 0)
    assert row is not None and (row.state, row.note) == (state, note)
    assert backend.writes == []  # never sent again
    assert backend.lookups == ([request_id] if lookup else [])
    if state == "done":
        assert row.result_json is not None and ISSUED in row.result_json


def test_the_lookup_at_a_start_is_told_the_row_and_no_consent(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite3"
    request_id = _left_sending(path)
    seen = []

    async def second() -> None:
        store = await SqliteOutbox.open(path)
        backend = Backend("answer", outbox=store, clock=FakeClock())
        made = an_action(backend, lookup=False)

        @made.lookup
        async def find(ctx: object, found: str) -> None:
            seen.append((ctx, found))

        await ActionRunner([made], outbox=store).reconcile(clock=FakeClock())
        await store.aclose()

    asyncio.run(second())
    [(ctx, found)] = seen
    assert found == request_id and ctx.request_id == request_id  # type: ignore[attr-defined]
    assert ctx.caller.subject == CALLER.subject and ctx.call_id == CALL_ID  # type: ignore[attr-defined]
    assert ctx.consent.words == "" and ctx.record == ()  # type: ignore[attr-defined]


def test_a_row_of_an_action_no_longer_declared_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite3"
    request_id = _left_sending(path)

    async def second() -> OutboxEntry | None:
        store = await SqliteOutbox.open(path)
        try:
            await ActionRunner([], outbox=store).reconcile(clock=FakeClock())
            return await store.get(request_id)
        finally:
            await store.aclose()

    row = asyncio.run(second())
    assert row is not None and (row.state, row.note) == ("flagged", "left, no_such_action")


def test_a_row_whose_write_is_under_way_here_is_left_to_its_job() -> None:
    rig = Rig("gated")

    async def scenario() -> tuple[int, str, str]:
        job = asyncio.ensure_future(rig.confirmed_run())
        await until(lambda: bool(rig.backend.writes))
        handled = await rig.runner.reconcile(clock=rig.clock)
        [(ctx, _)] = rig.backend.writes
        during = (await rig.outbox.get(ctx.request_id)).state  # type: ignore[union-attr]
        rig.backend.gate.set()
        await job
        after = (await rig.outbox.get(ctx.request_id)).state  # type: ignore[union-attr]
        return handled, during, after

    assert asyncio.run(scenario()) == (0, "sending", "done")


def test_a_runner_with_no_observer_runs_and_reconciles_with_its_system_clock() -> None:
    clock = FakeClock()
    outbox = MemoryOutbox()
    backend = Backend("answer", outbox=outbox, clock=clock)
    runner = ActionRunner([an_action(backend)], outbox=outbox)
    assert asyncio.run(runner.reconcile()) == 0
