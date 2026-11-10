"""The mock's modes (ole5_voice/tickets/mock.py), for the tests of invariant 6 and for a demo: a
refused write changes nothing; one that times out waits, then fails, having done nothing; one
answered late is done at once, so a lookup before its answer finds it, and it stays done when
its caller stops waiting; the reads answer by a mode of their own, and the page's listing by
none."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.tickets.mock import FILE_NAME, LATE_S, MODES, MockTicketSystem, Mode
from ole5_voice.tickets.system import TicketRef, TicketRefused, TicketTimeoutError
from t2_agentic_voice.actions.action import TIMEOUT_S

from tests.ole5_voice.tickets.ticket_support import CUSTOMER, mock, new_note, new_ticket, run

LATE = 0.05  # seconds: a late or timed-out call's wait in these tests
# The least a wait of LATE shows on the monotonic clock, which ticks every 15.6 ms on Windows.
WAITED = LATE - time.get_clock_info("monotonic").resolution
WRITES = ("create", "add_note")


def _write(tickets: MockTicketSystem, call: str, ticket_id: str) -> Coroutine[Any, Any, TicketRef]:
    """The write `call`: a second ticket (`req-2`), or a note (`req-note`) on `ticket_id`."""
    if call == "create":
        return tickets.create(new_ticket("req-2"))
    return tickets.add_note(new_note(ticket_id))


def _request(call: str) -> str:
    return "req-2" if call == "create" else "req-note"


def test_the_modes_and_a_wait_longer_than_an_actions_timeout() -> None:
    assert MODES == ("answer", "refuse", "timeout", "late")
    assert LATE_S > TIMEOUT_S


@pytest.mark.parametrize("call", WRITES)
def test_a_refused_write_changes_nothing(tmp_path: Path, call: str) -> None:
    tickets = mock(tmp_path)
    made = run(tickets.create(new_ticket()))
    before = (tmp_path / FILE_NAME).read_bytes()
    tickets.mode = "refuse"
    with pytest.raises(TicketRefused) as refused:
        run(_write(tickets, call, made.id))
    assert refused.value.reason == "refused"
    assert (tmp_path / FILE_NAME).read_bytes() == before
    assert run(tickets.find(_request(call), customer_email=CUSTOMER)) is None


@pytest.mark.parametrize("call", WRITES)
def test_a_write_that_times_out_waits_then_fails_having_done_nothing(
    tmp_path: Path, call: str
) -> None:
    tickets = mock(tmp_path, late_s=LATE)
    made = run(tickets.create(new_ticket()))
    before = (tmp_path / FILE_NAME).read_bytes()
    tickets.mode = "timeout"
    started = time.monotonic()
    with pytest.raises(TicketTimeoutError):
        run(_write(tickets, call, made.id))
    assert time.monotonic() - started >= WAITED
    assert (tmp_path / FILE_NAME).read_bytes() == before
    assert run(tickets.find(_request(call), customer_email=CUSTOMER)) is None


@pytest.mark.parametrize("call", WRITES)
def test_a_late_write_is_done_at_once_and_found_before_it_answers(
    tmp_path: Path, call: str
) -> None:
    tickets = mock(tmp_path, late_s=0.2)
    made = run(tickets.create(new_ticket()))
    tickets.mode = "late"

    async def scene() -> tuple[TicketRef | None, bool, TicketRef]:
        writing = asyncio.ensure_future(_write(tickets, call, made.id))
        await asyncio.sleep(0)  # the write runs until it waits to answer
        found = await tickets.find(_request(call), customer_email=CUSTOMER)
        return found, writing.done(), await writing

    found, answered_by_then, answer = run(scene())
    assert found == answer and answered_by_then is False


@pytest.mark.parametrize(("mode", "kept"), [("late", 1), ("timeout", 0)])
def test_a_write_its_caller_stops_waiting_for_stays_as_its_mode_left_it(
    tmp_path: Path, mode: Mode, kept: int
) -> None:
    """A late write cut by its caller's timeout is done, and found by its request ID; one that
    times out is not: the two cases a lookup tells apart (invariant 6)."""
    tickets = mock(tmp_path, mode=mode, late_s=5.0)

    async def scene() -> TicketRef | None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(tickets.create(new_ticket("req-cut")), timeout=LATE)
        return await tickets.find("req-cut", customer_email=CUSTOMER)

    found = run(scene())
    assert (found is not None) == bool(kept)
    assert len(mock(tmp_path).listed()) == kept  # in the file, as a restart would find it


@pytest.mark.parametrize("mode", ["refuse", "timeout"])
def test_the_reads_fail_by_their_own_mode_and_the_listing_by_none(
    tmp_path: Path, mode: Mode
) -> None:
    tickets = mock(tmp_path, late_s=LATE)
    made = run(tickets.create(new_ticket()))
    tickets.read_mode = mode
    failure = TicketRefused if mode == "refuse" else TicketTimeoutError
    with pytest.raises(failure):
        run(tickets.get(made.id, customer_email=CUSTOMER))
    with pytest.raises(failure):
        run(tickets.find("req-1", customer_email=CUSTOMER))
    assert len(tickets.listed()) == 1
    assert run(tickets.add_note(new_note(made.id))) == made  # the writes answer by theirs


def test_a_late_read_answers_after_its_wait(tmp_path: Path) -> None:
    tickets = mock(tmp_path, read_mode="late", late_s=LATE)
    made = run(tickets.create(new_ticket()))
    started = time.monotonic()
    got = run(tickets.get(made.id, customer_email=CUSTOMER))
    assert time.monotonic() - started >= WAITED
    assert got is not None and got.number == made.number
