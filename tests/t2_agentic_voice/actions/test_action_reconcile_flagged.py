"""`reconcile` asked to look the flagged rows up again too (`t2v outbox reconcile`; actions/
action_job.py; docs/SECURITY.md, invariant 6): a flagged row the lookup finds is `done`, with its
result; one it does not find, or of an action with no lookup or no longer declared, stays as it
was, its note kept; a row left `sending` is looked up as at a start; and nothing is ever sent
again. At a start (no `flagged`), a flagged row is not read."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

from tests.t2_agentic_voice.actions.action_support import (
    CALLER,
    ISSUED,
    Backend,
    RequestOpened,
    an_action,
)
from tests.t2_agentic_voice.fakes import WALL_START, FakeClock


def _row(request_id: str, state: OutboxState, note: str | None) -> OutboxEntry:
    values: dict[str, Any] = {
        "request_id": request_id,
        "call_id": "call-1",
        "subject": CALLER.subject,
        "action": "open_request",
        "draft_json": '{"category": "software", "summary": "made up"}',
        "state": state,
        "note": note,
        "created_at": WALL_START,
        "updated_at": WALL_START + timedelta(seconds=1),
    }
    return OutboxEntry.model_validate(values)


def _run(
    *rows: OutboxEntry, held: tuple[str, ...] = (), lookup: bool = True, flagged: bool = True
) -> tuple[int, dict[str, OutboxEntry], Backend]:
    async def scenario() -> tuple[int, dict[str, OutboxEntry], Backend]:
        store, clock = MemoryOutbox(), FakeClock()
        for row in rows:
            await store.add(row)
        backend = Backend("answer", outbox=store, clock=clock)
        for request_id in held:
            backend.held[request_id] = RequestOpened(number=ISSUED)
        runner = ActionRunner([an_action(backend, lookup=lookup)], outbox=store)
        handled = await runner.reconcile(clock=clock, flagged=flagged)
        return handled, {row.request_id: row for row in await store.entries()}, backend

    return asyncio.run(scenario())


def test_a_flagged_row_the_lookup_finds_is_done_with_its_result() -> None:
    handled, rows, backend = _run(_row("r-1", "flagged", "timed_out, not_found"), held=("r-1",))
    assert handled == 1 and (rows["r-1"].state, rows["r-1"].note) == ("done", "looked_up")
    assert rows["r-1"].result_json is not None and ISSUED in rows["r-1"].result_json
    assert backend.writes == [] and backend.lookups == ["r-1"]


@pytest.mark.parametrize("lookup", [True, False], ids=["not found", "no lookup"])
def test_a_flagged_row_not_found_stays_as_it_was_its_note_kept(lookup: bool) -> None:
    flagged = _row("r-1", "flagged", "timed_out, not_found")
    handled, rows, backend = _run(flagged, lookup=lookup)
    assert handled == 1 and rows["r-1"] == flagged
    assert backend.writes == []


def test_a_row_left_sending_is_looked_up_beside_the_flagged_ones() -> None:
    handled, rows, backend = _run(
        _row("r-1", "sending", None), _row("r-2", "flagged", "raised, not_found"), held=("r-1",)
    )
    assert handled == 2 and rows["r-1"].state == "done" and rows["r-2"].state == "flagged"
    assert backend.writes == [] and sorted(backend.lookups) == ["r-1", "r-2"]


def test_a_flagged_row_of_an_action_no_longer_declared_stays_as_it_was() -> None:
    flagged = _row("r-1", "flagged", "timed_out, no_lookup")

    async def scenario() -> OutboxEntry | None:
        store = MemoryOutbox()
        await store.add(flagged)
        await ActionRunner([], outbox=store).reconcile(clock=FakeClock(), flagged=True)
        return await store.get("r-1")

    assert asyncio.run(scenario()) == flagged


def test_at_a_start_a_flagged_row_is_not_read() -> None:
    handled, rows, backend = _run(_row("r-1", "flagged", "timed_out"), held=("r-1",), flagged=False)
    assert handled == 0 and rows["r-1"].state == "flagged" and backend.lookups == []
