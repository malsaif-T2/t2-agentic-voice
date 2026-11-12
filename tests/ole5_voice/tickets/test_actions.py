"""Ole5's actions over the mock ticket system (ole5_voice/tickets/actions.py), run as the library's
runner will run them once the caller said yes (plan 007's Track B), against a mock on each test's
own folder: a ticket made for the session's customer alone, whatever the draft says
(docs/SECURITY.md, invariant 3), its queue following its type; each failure given the meaning the
design's 6.4 gives it, a write with no reply looked up by its request ID and never sent twice
(invariant 6); a note only on a ticket made in this call; a handoff a request ticket with the
call's conversation attached (Q7). No error or log line holds a summary, a note or an email
(GP-19)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from ole5_voice.tickets.actions import (
    HANDOFF_TYPE,
    add_ticket_note,
    create_ticket,
    hand_off,
    has_customer,
)
from ole5_voice.tickets.drafts import HandoffDraft, NoteAdded, NoteDraft, TicketDraft, TicketMade
from ole5_voice.tickets.system import TicketRef, TicketTimeoutError
from ole5_voice.tickets.values import QUEUE_OF, TYPES
from t2_agentic_voice import ActionNotSent, ActionRejected, ConversationLine, ToolError

from tests.leaks import holding, shown
from tests.ole5_voice.tickets.action_support import action_context, call_context, recorded
from tests.ole5_voice.tickets.ticket_support import (
    CUSTOMER,
    NOTE,
    OTHER,
    SUMMARY,
    mock,
    new_ticket,
    run,
)

DRAFT = TicketDraft(summary=SUMMARY, type="Report")
# A summary that names another customer, as a caller may say one.
NAMING_OTHER = TicketDraft(summary=f"Open it for {OTHER}, not for me.", type="Bug")


def test_a_ticket_is_made_for_the_sessions_customer_whatever_the_draft_says(
    tmp_path: Path,
) -> None:
    """Invariant 3: the draft has no customer to give; a summary naming another customer's
    email makes the ticket the session's customer's, and the other sees nothing of it."""
    system = mock(tmp_path)
    made = create_ticket(system)
    result = run(made.execute(action_context("req-1"), NAMING_OTHER))
    assert isinstance(result, TicketMade)
    [kept] = system.listed()
    assert (kept.customer_email, kept.request_id, kept.number) == (CUSTOMER, "req-1", result.number)
    assert (kept.queue, kept.type, kept.priority) == ("Ole5 Technical", "Bug", "Medium")
    assert kept.transcript == ()
    assert run(system.get(kept.id, customer_email=OTHER)) is None
    assert run(system.find("req-1", customer_email=OTHER)) is None


def test_the_queue_follows_the_type_and_the_priority_is_the_drafts(tmp_path: Path) -> None:
    system = mock(tmp_path)
    made = create_ticket(system)
    for n, kind in enumerate(TYPES):
        draft = TicketDraft(summary=SUMMARY, type=kind, priority="High" if n % 2 else "Medium")
        run(made.execute(action_context(f"req-{n}"), draft))
    kept = system.listed()
    assert [(t.type, t.queue) for t in kept] == [(kind, QUEUE_OF[kind]) for kind in TYPES]
    assert [t.priority for t in kept] == ["High" if n % 2 else "Medium" for n in range(len(TYPES))]


def test_a_refusal_is_definitely_not_done_so_failed_is_said(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    system = mock(tmp_path, mode="refuse")
    for made, draft in (
        (create_ticket(system), DRAFT),
        (hand_off(system), HandoffDraft(summary=SUMMARY)),
    ):
        with pytest.raises(ActionRejected) as caught:
            run(made.execute(action_context(), draft))
        assert caught.value.details == {"reason": "refused"}
        for value in (SUMMARY, CUSTOMER):
            assert holding(value, shown(caught.value, caplog=caplog)) == []
    assert system.listed() == ()


def test_a_write_with_no_reply_is_found_by_its_request_id_and_made_once(tmp_path: Path) -> None:
    """Invariant 6: the mock does the write at once and answers late, past the runtime's wait;
    the lookup finds the ticket the write made, so `done` says its real number, and nothing
    is sent again."""
    system = mock(tmp_path, mode="late", late_s=5.0)
    made = create_ticket(system)

    async def scene() -> TicketMade | None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(made.execute(action_context("req-late"), DRAFT), 0.05)
        assert made.finder is not None
        found: TicketMade | None = await made.finder(action_context("req-late"), "req-late")
        return found

    found = run(scene())
    [kept] = system.listed()
    assert found is not None and found.number == kept.number
    assert made.finder is not None
    assert run(made.finder(action_context(), "req-never-sent")) is None


def test_a_timeout_is_no_refusal_so_the_runtime_looks_it_up(tmp_path: Path) -> None:
    """A timeout may have been done, so it is not `ActionRejected` (which would say `failed`):
    it reaches the runtime, which looks it up (here nothing was made) and says `unknown`."""
    system = mock(tmp_path, mode="timeout", late_s=0.01)
    made = create_ticket(system)
    with pytest.raises(TicketTimeoutError):
        run(made.execute(action_context("req-1"), DRAFT))
    assert made.finder is not None
    assert run(made.finder(action_context("req-1"), "req-1")) is None
    assert system.listed() == ()


def test_another_customers_call_never_finds_this_customers_write(tmp_path: Path) -> None:
    system = mock(tmp_path)
    made = create_ticket(system)
    run(made.execute(action_context("req-1"), DRAFT))
    assert made.finder is not None
    assert run(made.finder(action_context("req-1", email=OTHER), "req-1")) is None


def test_with_the_lookup_off_no_action_looks_a_write_up(tmp_path: Path) -> None:
    """The real system is thought to keep no request ID: with no lookup a write with no reply
    is `unknown`, flagged in the outbox, never sent again."""
    system = mock(tmp_path, lookup=False)
    for made in (create_ticket(system), add_ticket_note(system), hand_off(system)):
        assert made.finder is None
    system = mock(tmp_path)
    for made in (create_ticket(system), add_ticket_note(system), hand_off(system)):
        assert made.finder is not None


def test_a_call_whose_caller_names_no_customer_makes_nothing(tmp_path: Path) -> None:
    """A dev caller whose token named no customer: refused before the read-back, in words the
    talker reads; and were it sent, definitely not done."""
    system = mock(tmp_path)
    with pytest.raises(ToolError, match="no customer"):
        run(has_customer(call_context(email=None), DRAFT))
    assert run(has_customer(call_context(), DRAFT)) is DRAFT
    made = create_ticket(system)
    assert made.validate is has_customer
    with pytest.raises(ActionNotSent):
        run(made.execute(action_context(email=None), DRAFT))
    with pytest.raises(ActionNotSent):
        run(hand_off(system).execute(action_context(email=None), HandoffDraft(summary=SUMMARY)))
    assert system.listed() == ()


def test_a_note_goes_on_a_ticket_made_in_this_call(tmp_path: Path) -> None:
    system = mock(tmp_path)
    ref = run(system.create(new_ticket("req-made")))
    made = add_ticket_note(system)
    record = (recorded("create_ticket", ref),)
    draft = NoteDraft(ticket_ends_in=ref.number[-4:], note=NOTE)
    assert made.validate is not None
    assert run(made.validate(call_context(record=record), draft)) is draft
    result = run(made.execute(action_context("req-note", record=record), draft))
    assert result == NoteAdded(ticket_id=ref.id, number=ref.number, last_four=ref.number[-4:])
    [kept] = system.listed()
    assert [(n.request_id, n.text) for n in kept.notes] == [("req-note", NOTE)]
    assert made.finder is not None
    assert run(made.finder(action_context(), "req-note")) == result


def test_a_note_on_any_ticket_this_call_did_not_make_is_refused_before_the_read_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Invariant 3: a number the caller says, their own older ticket's or another customer's,
    is no ticket of this call; the talker is told so, in fixed words."""
    caplog.set_level("DEBUG")
    system = mock(tmp_path)
    mine = run(system.create(new_ticket("req-made")))
    theirs = run(system.create(new_ticket("req-theirs", customer=OTHER)))
    made = add_ticket_note(system)
    record = (recorded("create_ticket", mine),)
    assert made.validate is not None
    for number in (theirs.number, "2026110582000012"):
        draft = NoteDraft(ticket_ends_in=number[-4:], note=NOTE)
        with pytest.raises(ToolError, match="No ticket made in this call") as caught:
            run(made.validate(call_context(record=record), draft))
        for value in (NOTE, number[-4:], OTHER):
            assert holding(value, shown(caught.value, caplog=caplog)) == []
        with pytest.raises(ActionNotSent):
            run(made.execute(action_context(record=record), draft))
    with pytest.raises(ToolError, match="no customer"):
        draft = NoteDraft(ticket_ends_in=mine.number[-4:], note=NOTE)
        run(made.validate(call_context(record=record, email=None), draft))
    assert all(ticket.notes == () for ticket in system.listed())


def test_a_record_naming_another_customers_ticket_is_still_refused_by_the_system(
    tmp_path: Path,
) -> None:
    """Were a record to hold another customer's ticket, the ticket system itself refuses a note
    on it for this customer, so `failed` is said and their ticket is unchanged."""
    system = mock(tmp_path)
    theirs = run(system.create(new_ticket("req-theirs", customer=OTHER)))
    made = add_ticket_note(system)
    record = (recorded("create_ticket", theirs),)
    draft = NoteDraft(ticket_ends_in=theirs.number[-4:], note=NOTE)
    with pytest.raises(ActionRejected) as caught:
        run(made.execute(action_context(record=record), draft))
    assert caught.value.details == {"reason": "not_found"}
    [kept] = system.listed()
    assert kept.notes == () and kept.customer_email == OTHER


def test_two_tickets_of_this_call_ending_alike_are_asked_about(tmp_path: Path) -> None:
    first = TicketRef(id="1", number="2026111082000917")
    second = TicketRef(id="2", number="2026111182000917")
    record = (recorded("create_ticket", first), recorded("hand_off", second, "req-2"))
    made = add_ticket_note(mock(tmp_path))
    assert made.validate is not None
    with pytest.raises(ToolError, match="Two tickets"):
        run(made.validate(call_context(record=record), NoteDraft(ticket_ends_in="0917", note=NOTE)))


def test_a_handoff_is_a_request_ticket_with_the_calls_conversation(tmp_path: Path) -> None:
    """Q7 and D-009: support staff read the summary the caller heard, with what both sides said,
    taken from the session and never from the talker."""
    system = mock(tmp_path)
    said = (
        ConversationLine(speaker="caller", text="The made-up inbox will not load."),
        ConversationLine(speaker="agent", text="Here is what the guide says."),
        ConversationLine(speaker="caller", text="I would rather talk to a person."),
    )
    made = hand_off(system)
    result = run(
        made.execute(action_context("req-hand", conversation=said), HandoffDraft(summary=SUMMARY))
    )
    [kept] = system.listed()
    assert (kept.type, kept.queue, kept.priority) == (HANDOFF_TYPE, QUEUE_OF["Request"], "Medium")
    assert (kept.customer_email, kept.summary, kept.transcript) == (CUSTOMER, SUMMARY, said)
    assert result == TicketMade.of(TicketRef(id=kept.id, number=kept.number))
    assert made.max_per_call == 1  # one handoff ticket a call (D-009)


def test_the_note_tool_sends_a_change_to_a_ticket_only_read_back_to_create_ticket(
    tmp_path: Path,
) -> None:
    """The live call `_Hdmiy0vDE` (2026-11-12): "mention in the ticket that ..." after a stopped
    read-back was taken for a note, and the caller was asked for the digits of a ticket never
    made. The note tool's description says a change to a ticket not yet made goes to its draft."""
    description = add_ticket_note(mock(tmp_path)).description
    assert "never for one only read back and not yet made" in description
    assert "call create_ticket again with it" in description
