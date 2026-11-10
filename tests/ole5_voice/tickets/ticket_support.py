"""What the tests of Ole5's tickets share: made-up customers, a ticket to create, a clock that
moves only when a test moves it, and the mock on a test's own folder."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

from ole5_voice.tickets.mock import RIYADH, MockTicketSystem
from ole5_voice.tickets.system import NewNote, NewTicket

CUSTOMER = "made-up.customer@example.com"
OTHER = "someone.else@example.com"
SUMMARY = "The made-up report page shows no rows since this morning."
NOTE = "The made-up report is the monthly one, not the weekly one."
# 10 November 2026, 09:30 in Riyadh.
MORNING = datetime(2026, 11, 10, 9, 30, tzinfo=RIYADH)


class Clock:
    """A clock that says `now` until a test changes it."""

    def __init__(self, now: datetime = MORNING) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def new_ticket(request_id: str = "req-1", customer: str = CUSTOMER, **given: Any) -> NewTicket:
    """A ticket to create for `customer`, with `given` in place of the made-up fields."""
    fields: dict[str, Any] = {"queue": "Ole5 Support", "type": "Inquiry", "summary": SUMMARY}
    fields |= given
    return NewTicket(request_id=request_id, customer_email=customer, **fields)


def new_note(ticket_id: str, request_id: str = "req-note", customer: str = CUSTOMER) -> NewNote:
    """A note to add to `ticket_id` for `customer`."""
    return NewNote(request_id=request_id, customer_email=customer, ticket_id=ticket_id, text=NOTE)


def mock(folder: Path, clock: Clock | None = None, **given: Any) -> MockTicketSystem:
    """The mock kept in `folder`, on `clock` (a new one unless given)."""
    return MockTicketSystem(folder, clock=clock or Clock(), **given)


def run[T](scene: Coroutine[Any, Any, T]) -> T:
    """`scene`, run to its end on a new event loop."""
    return asyncio.run(scene)
