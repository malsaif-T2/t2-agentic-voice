"""The mock ticket system (ole5_voice/tickets/mock.py): its numbers in the real shape, its
tickets kept across a reopen, nothing touched until it is used, the lookup by request ID and
switching it off, and every read and note scoped by the customer's email (docs/SECURITY.md,
invariant 3). Its modes are test_mock_modes.py's. Every folder is the test's own."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from ole5_voice.tickets.mock import FILE_NAME, MockTicket, MockTicketSystem
from ole5_voice.tickets.system import (
    NUMBER_PATTERN,
    LookupUnavailableError,
    Ticket,
    TicketRefused,
    TicketSystem,
)
from ole5_voice.tickets.values import NEW_STATUS
from t2_agentic_voice import ConfigurationError, ConversationLine

from tests.leaks import holding, shown
from tests.ole5_voice.tickets.ticket_support import (
    CUSTOMER,
    MORNING,
    NOTE,
    OTHER,
    SUMMARY,
    Clock,
    mock,
    new_note,
    new_ticket,
    run,
)


def test_the_mock_is_a_ticket_system(tmp_path: Path) -> None:
    system: TicketSystem = mock(tmp_path)
    assert system.can_find is True


def test_numbers_are_the_date_82_and_a_counter_that_starts_again_each_day(tmp_path: Path) -> None:
    clock = Clock()
    tickets = mock(tmp_path, clock)
    first = run(tickets.create(new_ticket("req-1")))
    second = run(tickets.create(new_ticket("req-2")))
    clock.now = MORNING + timedelta(days=1)
    next_day = run(tickets.create(new_ticket("req-3")))
    assert [first.number, second.number, next_day.number] == [
        "2026111082000001",
        "2026111082000002",
        "2026111182000001",
    ]
    assert all(re.fullmatch(NUMBER_PATTERN, made.number) for made in (first, second, next_day))
    assert all(len(made.number) == 16 for made in (first, second, next_day))
    assert [first.id, second.id, next_day.id] == ["1", "2", "3"]


def test_the_counter_goes_on_after_a_reopen_and_stops_at_six_digits(tmp_path: Path) -> None:
    run(mock(tmp_path).create(new_ticket("req-1")))
    assert run(mock(tmp_path).create(new_ticket("req-2"))).number == "2026111082000002"
    kept = json.loads((tmp_path / FILE_NAME).read_text(encoding="utf-8"))
    kept["tickets"][-1]["number"] = "2026111082999999"
    (tmp_path / FILE_NAME).write_text(json.dumps(kept), encoding="utf-8")
    with pytest.raises(TicketRefused) as refused:
        run(mock(tmp_path).create(new_ticket("req-3")))
    assert refused.value.reason == "full"
    assert len(mock(tmp_path).listed()) == 2  # nothing made


def test_tickets_and_their_notes_are_kept_across_a_reopen(tmp_path: Path) -> None:
    said = (
        ConversationLine(speaker="caller", text="made-up words of the caller"),
        ConversationLine(speaker="agent", text="made-up words of the agent"),
    )
    made = run(mock(tmp_path).create(new_ticket(priority="High", transcript=said)))
    noted = run(mock(tmp_path).add_note(new_note(made.id)))
    assert noted == made
    reopened = mock(tmp_path)
    got = run(reopened.get(made.id, customer_email=CUSTOMER))
    assert got == Ticket(
        id=made.id,
        number=made.number,
        queue="Ole5 Support",
        type="Inquiry",
        priority="High",
        status=NEW_STATUS,
        summary=SUMMARY,
        created_at=MORNING,
    )
    assert type(got) is Ticket  # no request ID, email, transcript or note in what `get` gives
    [kept] = reopened.listed()
    assert isinstance(kept, MockTicket)
    assert (kept.request_id, kept.customer_email, kept.transcript) == ("req-1", CUSTOMER, said)
    assert [(note.request_id, note.text) for note in kept.notes] == [("req-note", NOTE)]


def test_the_mock_touches_nothing_until_used_and_makes_its_folder_on_its_first_write(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "var" / "ole5" / "tickets"
    tickets = MockTicketSystem(folder)
    assert not (tmp_path / "var").exists()
    assert run(tickets.get("1", customer_email=CUSTOMER)) is None
    assert tickets.listed() == ()
    assert not (tmp_path / "var").exists()  # a read makes nothing
    run(tickets.create(new_ticket()))
    assert sorted(p.name for p in folder.iterdir()) == [FILE_NAME]  # no temporary file left


def test_a_write_is_found_by_its_request_id_a_note_by_its_own(tmp_path: Path) -> None:
    tickets = mock(tmp_path)
    made = run(tickets.create(new_ticket("req-made")))
    run(tickets.add_note(new_note(made.id, request_id="req-noted")))
    assert run(tickets.find("req-made", customer_email=CUSTOMER)) == made
    assert run(tickets.find("req-noted", customer_email=CUSTOMER)) == made
    assert run(tickets.find("req-never", customer_email=CUSTOMER)) is None


def test_the_lookup_switched_off_finds_nothing_and_says_so(tmp_path: Path) -> None:
    tickets = mock(tmp_path, lookup=False)
    assert tickets.can_find is False
    run(tickets.create(new_ticket("req-made")))  # writes still answer
    with pytest.raises(LookupUnavailableError):
        run(tickets.find("req-made", customer_email=CUSTOMER))
    tickets.can_find = True  # a test switches it on again
    assert run(tickets.find("req-made", customer_email=CUSTOMER)) is not None


def test_a_request_id_sent_twice_makes_two_tickets(tmp_path: Path) -> None:
    """The mock never dedupes, so a write the runtime sent twice shows."""
    tickets = mock(tmp_path)
    first = run(tickets.create(new_ticket("req-same")))
    second = run(tickets.create(new_ticket("req-same")))
    assert first != second and len(tickets.listed()) == 2
    assert run(tickets.find("req-same", customer_email=CUSTOMER)) == first


def test_another_customers_ticket_is_never_read_found_or_noted(tmp_path: Path) -> None:
    """Invariant 3: a ticket is read as the customer the call's session names, whatever was
    said; one whose summary names another customer's email is still its own customer's."""
    tickets = mock(tmp_path)
    theirs = run(tickets.create(new_ticket("req-theirs", customer=OTHER)))
    mine = run(tickets.create(new_ticket("req-mine", summary=f"Please use {OTHER} instead.")))
    assert run(tickets.get(theirs.id, customer_email=CUSTOMER)) is None
    assert run(tickets.find("req-theirs", customer_email=CUSTOMER)) is None
    assert run(tickets.get(mine.id, customer_email=OTHER)) is None
    assert run(tickets.find("req-mine", customer_email=OTHER)) is None
    with pytest.raises(TicketRefused) as refused:
        run(tickets.add_note(new_note(theirs.id, customer=CUSTOMER)))
    assert refused.value.reason == "not_found"
    assert all(t.notes == () for t in tickets.listed())
    assert holding(OTHER, shown(refused.value)) == holding(NOTE, shown(refused.value)) == []
    shouted = f"  {CUSTOMER.upper()} "
    assert run(tickets.get(mine.id, customer_email=shouted)) is not None  # one customer, any case
    with pytest.raises(TicketRefused):
        run(tickets.add_note(new_note("no-such-ticket")))


def test_a_file_that_is_not_the_mocks_is_refused_by_name_never_by_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILE_NAME).write_text(
        json.dumps({"tickets": [{"summary": SUMMARY, "customer_email": OTHER}]}), encoding="utf-8"
    )
    with pytest.raises(ConfigurationError) as caught:
        mock(tmp_path).listed()
    assert FILE_NAME in caught.value.message and "FIX:" in caught.value.message
    surfaces = shown(caught.value, caplog=caplog)
    assert holding(SUMMARY, surfaces) == holding(OTHER, surfaces) == []


def test_no_log_line_holds_a_tickets_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    tickets = mock(tmp_path)
    made = run(tickets.create(new_ticket()))
    run(tickets.add_note(new_note(made.id)))
    run(tickets.get(made.id, customer_email=CUSTOMER))
    tickets.mode = "refuse"
    with pytest.raises(TicketRefused):
        run(tickets.create(new_ticket("req-2")))
    surfaces = shown(caplog=caplog)
    for value in (SUMMARY, NOTE, CUSTOMER, made.number):
        assert holding(value, surfaces) == []
    assert [r.getMessage() for r in caplog.records if r.name == "ole5_voice.tickets.mock"] == [
        "mock_ticket_written",
        "mock_ticket_written",
        "mock_ticket_refused",
    ]
