"""The values an Ole5 ticket is made of (ole5_voice/tickets/values.py), as the prototype's sheet
names them, and the ticket system's data parsing them strictly (ole5_voice/tickets/system.py;
docs/SECURITY.md, invariant 4): a value outside a fixed set, a summary over 200 characters or a
field the data does not hold is refused, the error's text holding none of the values given."""

from __future__ import annotations

from typing import Any

import pytest
from ole5_voice.tickets.system import MAX_SUMMARY_CHARS, NewNote, NewTicket, TicketRef
from ole5_voice.tickets.values import (
    CLOSED,
    DEFAULT_PRIORITY,
    NEW_STATUS,
    PRIORITIES,
    QUEUE_OF,
    QUEUES,
    STATUSES,
    TYPES,
)
from pydantic import ValidationError

from tests.leaks import holding
from tests.ole5_voice.tickets.ticket_support import CUSTOMER, new_ticket


def test_the_values_are_the_sheets() -> None:
    assert QUEUES == ("Ole5 Support", "Ole5 Technical")
    assert len(TYPES) == 11 and len(set(TYPES)) == 11
    assert {"Bug", "Inquiry", "Reset Password", "Request for Migration"} <= set(TYPES)
    assert PRIORITIES == ("Low", "Medium", "High", "Critical")
    assert len(STATUSES) == 9 and STATUSES[0] == NEW_STATUS == "New"
    assert sorted(CLOSED) == ["closed successful", "merged"]
    assert CLOSED.issubset(STATUSES)
    assert DEFAULT_PRIORITY == "Medium"


def test_every_type_goes_to_one_of_the_queues() -> None:
    assert tuple(QUEUE_OF) == TYPES
    assert set(QUEUE_OF.values()) == set(QUEUES)


def test_a_new_ticket_takes_medium_unless_told() -> None:
    assert new_ticket().priority == "Medium"


@pytest.mark.parametrize(
    "given",
    [
        {"type": "Urgent Refund"},
        {"queue": "Ole5 Billing"},
        {"priority": "Highest"},
        {"type": "bug"},  # the sheet's case, never another
        {"summary": "x" * (MAX_SUMMARY_CHARS + 1)},
        {"summary": ""},
        {"confirmed": True},
        {"status": "closed successful"},
    ],
)
def test_a_value_outside_its_set_or_a_field_it_does_not_hold_is_refused(
    given: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as caught:
        new_ticket(**given)
    for value in given.values():
        if isinstance(value, str) and value:
            assert holding(value, {"message": str(caught.value)}) == []  # its text hides it


def test_a_note_and_a_ticket_number_are_parsed_too() -> None:
    with pytest.raises(ValidationError):
        NewNote(request_id="r", customer_email=CUSTOMER, ticket_id="1", text="x" * 1001)
    for number in ("2026111082000001x", "202611108200001", "2026111083000001", "T-MOCK-1"):
        with pytest.raises(ValidationError):
            TicketRef(id="1", number=number)
    with pytest.raises(ValidationError):
        NewTicket.model_validate(
            {"request_id": "", "customer_email": CUSTOMER, "queue": "Ole5 Support"}
        )
