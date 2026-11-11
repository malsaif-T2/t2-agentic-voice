"""Ole5's ticket status (ole5_voice/tickets/status.py): a read tool that reports on the actions
that make a ticket; the caller's customer bound from the session, never shown to the talker;
only the tickets the outbox holds for this caller, each read from the system for that customer;
a number matched only among them, said back by its last four digits (plan 007's Q4 and Q6).

Invariant 3's adversarial cases (docs/SECURITY.md): a caller naming another customer's ticket
number, or an email, gets nothing of theirs, whatever the outbox holds. The outbox is a fake
(`PastContext`): `past_actions` is the library's, built by plan 007's Track B."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.customer import CUSTOMER_FIELD
from ole5_voice.tickets.status import (
    LISTED,
    TICKET_STATUS,
    StatusAnswer,
    said_digits,
    ticket_status,
)
from ole5_voice.tickets.system import TicketRef
from pydantic import ValidationError
from t2_agentic_voice import Tool, ToolError

from tests.leaks import holding, shown
from tests.ole5_voice.tickets.action_support import PastContext, call_context, recorded
from tests.ole5_voice.tickets.ticket_support import (
    CUSTOMER,
    MORNING,
    OTHER,
    SUMMARY,
    Clock,
    mock,
    new_ticket,
    run,
)

THEIR_SUMMARY = "Someone else's made-up archive will not open."


def _status(tool: Tool, ctx: PastContext, **arguments: Any) -> StatusAnswer:
    """`tool` called as the library's runner calls it: the talker's arguments parsed, the
    customer bound from the caller."""
    parsed = tool.parameters.model_validate(arguments)
    customer = tool.bind["customer"].value(ctx.caller)
    answer = run(tool.function(ctx=ctx, customer=customer, **parsed.model_dump()))
    assert isinstance(answer, StatusAnswer)
    return answer


class _Scene:
    """The mock with the caller's two tickets, made through the agent, one made otherwise, and
    another customer's; the outbox of this caller."""

    def __init__(self, folder: Path) -> None:
        clock = Clock()
        self.system = mock(folder, clock)
        self.first = run(self.system.create(new_ticket("req-1")))
        clock.now = MORNING + timedelta(hours=1)
        self.handed = run(self.system.create(new_ticket("req-2", type="Request")))
        self.elsewhere = run(self.system.create(new_ticket("req-3")))
        self.theirs = run(
            self.system.create(new_ticket("req-4", customer=OTHER, summary=THEIR_SUMMARY))
        )
        self.past = (
            recorded("create_ticket", self.first, "req-1"),
            recorded("hand_off", self.handed, "req-2"),
        )
        self.tool = ticket_status(self.system)


def test_the_status_reports_on_the_ticket_makers_and_hides_the_customer(tmp_path: Path) -> None:
    tool = _Scene(tmp_path).tool
    assert tool.name == TICKET_STATUS
    assert tool.reports_on == ("create_ticket", "hand_off")
    assert tool.bind["customer"].field == CUSTOMER_FIELD
    schema: Any = tool.tool_schema().parameters
    assert set(schema["properties"]) == {"number"}  # no email, no customer, no subject
    for invented in ({"customer": OTHER}, {"customer_email": OTHER}, {"email": OTHER}):
        with pytest.raises(ValidationError):
            tool.parameters.model_validate({"number": "0001", **invented})


def test_the_caller_hears_only_their_tickets_made_through_the_agent(tmp_path: Path) -> None:
    """Q4: the outbox is the list; a ticket of theirs made any other way, and another
    customer's, are not in it. Each is said by its last four digits (Q6)."""
    scene = _Scene(tmp_path)
    answer = _status(scene.tool, call_context(past=scene.past))
    assert [(t.ends_in, t.by) for t in answer.tickets] == [
        (scene.first.number[-4:], "create_ticket"),
        (scene.handed.number[-4:], "hand_off"),
    ]
    assert answer.total == 2 and answer.asked_ends_in is None
    first = answer.tickets[0]
    assert (first.type, first.status, first.closed) == ("Inquiry", "New", False)
    # The priority is internal (the owner's ruling of 2026-11-11): the talker is never told it.
    assert "priority" not in type(first).model_fields
    assert "priority" not in answer.model_dump_json()
    assert (first.summary, first.opened_on) == (SUMMARY, "2026-11-10")
    data = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
    for number in (scene.first.number, scene.handed.number):
        assert number not in data  # the whole number is never given in a status
    for value in (scene.elsewhere.number[-4:], scene.theirs.number[-4:], THEIR_SUMMARY, OTHER):
        assert value not in data


def test_a_number_the_caller_says_is_matched_only_among_their_tickets(tmp_path: Path) -> None:
    scene = _Scene(tmp_path)
    ctx = call_context(past=scene.past)
    for said in (scene.first.number, scene.first.number[-4:], scene.first.number[-6:]):
        answer = _status(scene.tool, ctx, number=said)
        assert [t.ends_in for t in answer.tickets] == [scene.first.number[-4:]]
        assert answer.asked_ends_in == scene.first.number[-4:]  # said back first
    arabic = said_digits("".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in scene.handed.number[-4:]))
    assert _status(scene.tool, ctx, number=arabic).tickets[0].ends_in == scene.handed.number[-4:]


def test_another_customers_number_gives_nothing_of_theirs(tmp_path: Path) -> None:
    """Invariant 3: the caller says another customer's ticket number, whole or its last four,
    or names their email beside it; the answer holds nothing of that ticket, not even whether
    it exists. Invariant 2: nor are the said digits given back, since a status result backs a
    claim of the ticket makers (rule A); a talker's clause naming them would pass as made."""
    scene = _Scene(tmp_path)
    ctx = call_context(past=scene.past)
    for said in (scene.theirs.number, scene.theirs.number[-4:], f"{scene.theirs.number} {OTHER}"):
        answer = _status(scene.tool, ctx, number=said)
        assert answer.tickets == () and answer.total == 0
        assert answer.asked_ends_in is None
        assert "None of the caller's tickets" in answer.note
        data = json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
        for value in (scene.theirs.number[-4:], THEIR_SUMMARY, OTHER, "Ole5 Support", "Inquiry"):
            assert value not in data
        assert "New" not in data


def test_digits_matching_none_of_the_callers_tickets_are_not_given_back(tmp_path: Path) -> None:
    """Invariant 2: a number never issued, or one a passage made up, said as the caller's, is
    not in the result, so it backs no claim that a ticket was made (rule A)."""
    scene = _Scene(tmp_path)
    taken = {scene.first.number[-4:], scene.handed.number[-4:]}
    unissued = next(f"{n:04d}" for n in range(10_000) if f"{n:04d}" not in taken)
    for said in (unissued, f"2026 1110 8200 {unissued}"):
        answer = _status(scene.tool, call_context(past=scene.past), number=said)
        assert answer.tickets == () and answer.asked_ends_in is None
        assert unissued not in json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)


def test_an_outbox_row_of_another_customers_ticket_shows_nothing(tmp_path: Path) -> None:
    """Were the outbox to hold another customer's ticket (an older row, made while the
    settings named that customer), the system reads it for the session's customer and finds
    none, so the status says nothing of it."""
    scene = _Scene(tmp_path)
    forged = (*scene.past, recorded("create_ticket", scene.theirs, "req-4"))
    answer = _status(scene.tool, call_context(past=forged))
    assert scene.theirs.number[-4:] not in [t.ends_in for t in answer.tickets]
    assert THEIR_SUMMARY not in json.dumps(answer.model_dump(mode="json"), ensure_ascii=False)
    # Its number said: the outbox row matches, the system holds none for this caller, and the
    # said digits are not given back either.
    named = _status(scene.tool, call_context(past=forged), number=scene.theirs.number)
    assert named.tickets == () and named.asked_ends_in is None
    assert scene.theirs.number[-4:] not in json.dumps(named.model_dump(mode="json"))
    # A row whose ID now names another of the caller's tickets is not taken for it.
    moved = recorded("create_ticket", TicketRef(id=scene.first.id, number=scene.elsewhere.number))
    assert _status(scene.tool, call_context(past=(moved,))).tickets == ()


def test_the_same_outbox_read_as_another_customer_shows_none_of_these(tmp_path: Path) -> None:
    scene = _Scene(tmp_path)
    answer = _status(scene.tool, call_context(past=scene.past, email=OTHER))
    assert answer.tickets == ()


def test_a_number_too_short_or_too_long_is_asked_again(tmp_path: Path) -> None:
    tool = _Scene(tmp_path).tool
    ctx = call_context()
    for said, words in (
        ("917", "at least the last four"),
        ("1" * 17, "16 digits"),
        ("no digits", "at least"),
    ):
        with pytest.raises(ToolError, match=words) as caught:
            _status(tool, ctx, number=said)
        assert holding(said, shown(caught.value)) == []


def test_only_the_newest_tickets_are_listed(tmp_path: Path) -> None:
    system = mock(tmp_path)
    made = [run(system.create(new_ticket(f"req-{n}"))) for n in range(LISTED + 2)]
    past = tuple(recorded("create_ticket", ref, f"req-{n}") for n, ref in enumerate(made))
    answer = _status(ticket_status(system), call_context(past=past))
    assert [t.ends_in for t in answer.tickets] == [ref.number[-4:] for ref in made[-LISTED:]]
    assert answer.total == LISTED + 2


def test_a_ticket_system_that_fails_is_said_plainly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    scene = _Scene(tmp_path)
    scene.system.read_mode = "refuse"
    with pytest.raises(ToolError, match="cannot check their tickets") as caught:
        _status(scene.tool, call_context(past=scene.past), number=scene.first.number)
    for value in (scene.first.number, CUSTOMER, SUMMARY):
        assert holding(value, shown(caught.value, caplog=caplog)) == []


def test_digits_are_read_as_the_guard_reads_them() -> None:
    assert said_digits("2026 1110-8200 0917") == "2026111082000917"
    assert said_digits("٠٩١٧") == "0917"
    assert said_digits("ending in 0917.") == "0917"
