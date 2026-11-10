"""Ole5's actions over a ticket system (plan 007; the design's 4.4 and 6.4), each read back and
confirmed like any action, each reaching the system by a closure, as `knowledge_tool` reaches
its knowledge base (D-080):

- **`create_ticket`**: a ticket from the caller's problem (drafts.py's `TicketDraft`), its queue
  the one its type goes to, its number said whole, in groups, once it is made (Q5, Q6).
- **`add_ticket_note`**: a note on a ticket made in this call, named by its last four digits,
  for a correction once it is made.
- **`hand_off`**: the caller's request for a person, as a ticket for support staff with the
  call's conversation attached; there is no live transfer (D-009, D-018, Q7).

Who the ticket is for is the session's caller (customer.py), never a value of the draft: the
talker cannot name another customer (docs/SECURITY.md, invariant 3). A call whose caller names
no customer is refused before the read-back (`validate`), and never sent. A note goes only on a
ticket this call's record holds, and the ticket system itself refuses one on another
customer's ticket.

How each failure is spoken (the design's 6.4): the system's refusal (`TicketRefused`) is
`ActionRejected`, so `failed` is said; a write with no customer is `ActionNotSent`; anything
else, a timeout among them, may have been done, so the runtime looks it up by its request ID
(`find`, registered only when the system can find one, invariant 6) and says `unknown` when it
finds nothing.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import (
    Action,
    ActionContext,
    ActionNotSent,
    ActionRejected,
    CallContext,
    ToolError,
    action,
)

from ole5_voice.customer import customer_email
from ole5_voice.tickets import lines
from ole5_voice.tickets.drafts import (
    ADD_NOTE,
    CREATE_TICKET,
    HAND_OFF,
    HandoffDraft,
    NoteAdded,
    NoteDraft,
    TicketDraft,
    TicketMade,
    made_in,
)
from ole5_voice.tickets.system import NewNote, NewTicket, TicketRefused, TicketSystem
from ole5_voice.tickets.values import DEFAULT_PRIORITY, QUEUE_OF, TicketType

# A handoff's ticket: a request to support staff, at the default priority.
HANDOFF_TYPE: Final[TicketType] = "Request"
# How many of each a call may do: two tickets, two notes, one handoff (D-009).
TICKETS_PER_CALL: Final = 2
NOTES_PER_CALL: Final = 2
HANDOFFS_PER_CALL: Final = 1

CREATE_DESCRIPTION: Final = (
    "Open a support ticket for the caller's Ole5 problem, only when the caller wants one. "
    "First learn what is wrong and how urgent it is, asking in one short question for "
    "whichever the caller has not said; ask for nothing else. "
    "Write the summary yourself and pick the type that fits. The caller hears the ticket read "
    "back and is asked to confirm it; say nothing yourself after calling this."
)
NOTE_DESCRIPTION: Final = (
    "Add a note to a ticket made earlier in this call, to correct it or add to it once it is "
    "made. Give the last four digits of that ticket's number and the note. Only for a ticket "
    "made in this call. The caller hears the note read back and is asked to confirm it; say "
    "nothing yourself after calling this."
)
HANDOFF_DESCRIPTION: Final = (
    "Pass the caller's request to Ole5's support team as a ticket, when the caller asks for a "
    "person, a staff member or a human. There is no live transfer: support staff read the "
    "ticket, with what was said in this call. Write the summary of what the caller needs. The "
    "caller hears it read back and is asked to confirm it; say nothing yourself after calling "
    "this."
)
_NO_CUSTOMER: Final = (
    "This call has no customer to open a ticket for, so no ticket can be made in it. Tell the "
    "caller plainly that you cannot do that in this call."
)


async def has_customer[D](ctx: CallContext, draft: D) -> D:
    """`draft` as it is, when the call's caller names a customer; ToolError, which the talker
    reads, when not."""
    if customer_email(ctx.caller) is None:
        raise ToolError(_NO_CUSTOMER)
    return draft


def _customer(ctx: CallContext) -> str:
    """The session's customer; ActionNotSent, nothing sent, when the caller names none."""
    email = customer_email(ctx.caller)
    if email is None:
        raise ActionNotSent("The call's caller names no customer.")
    return email


def _rejected(error: TicketRefused) -> ActionRejected:
    return ActionRejected(error.message, details={"reason": error.reason})


def create_ticket(system: TicketSystem) -> Action:
    """The action that opens a ticket on `system` (the module's docstring)."""

    @action(
        name=CREATE_TICKET,
        description=CREATE_DESCRIPTION,
        read_back=lines.TICKET_READ_BACK,
        done=lines.TICKET_DONE,
        claims=lines.TICKET_CLAIMS,
        sending=lines.TICKET_SENDING,
        failed=lines.TICKET_FAILED,
        unknown=lines.TICKET_UNKNOWN,
        declined=lines.TICKET_DECLINED,
        validate=has_customer,
        max_per_call=TICKETS_PER_CALL,
    )
    async def opened(ctx: ActionContext, draft: TicketDraft) -> TicketMade:
        ticket = NewTicket(
            request_id=ctx.request_id,
            customer_email=_customer(ctx),
            queue=QUEUE_OF[draft.type],
            type=draft.type,
            priority=draft.priority,
            summary=draft.summary,
        )
        try:
            return TicketMade.of(await system.create(ticket))
        except TicketRefused as error:
            raise _rejected(error) from error

    if system.can_find:

        @opened.lookup
        async def found(ctx: ActionContext, request_id: str) -> TicketMade | None:
            ref = await system.find(request_id, customer_email=_customer(ctx))
            return None if ref is None else TicketMade.of(ref)

    return opened


def _made_here(ctx: CallContext, ends_in: str) -> TicketMade:
    """The one ticket this call's record holds whose number ends in `ends_in`; ToolError, which
    the talker reads, when it holds none or two."""
    found = [made for _, made in made_in(ctx.record) if made.last_four == ends_in]
    if not found:
        raise ToolError(
            "No ticket made in this call ends in those digits. A note goes only on a ticket made "
            "in this call; ask the caller which one they mean."
        )
    if len(found) > 1:
        raise ToolError(
            "Two tickets made in this call end in those digits; ask the caller which one."
        )
    return found[0]


async def _on_a_ticket_made_here(ctx: CallContext, draft: NoteDraft) -> NoteDraft:
    await has_customer(ctx, draft)
    _made_here(ctx, draft.ticket_ends_in)
    return draft


def add_ticket_note(system: TicketSystem) -> Action:
    """The action that adds a note to a ticket made in this call, on `system` (the module's
    docstring)."""

    @action(
        name=ADD_NOTE,
        description=NOTE_DESCRIPTION,
        read_back=lines.NOTE_READ_BACK,
        done=lines.NOTE_DONE,
        claims=lines.NOTE_CLAIMS,
        sending=lines.NOTE_SENDING,
        failed=lines.NOTE_FAILED,
        unknown=lines.NOTE_UNKNOWN,
        declined=lines.NOTE_DECLINED,
        validate=_on_a_ticket_made_here,
        max_per_call=NOTES_PER_CALL,
    )
    async def noted(ctx: ActionContext, draft: NoteDraft) -> NoteAdded:
        try:
            ticket = _made_here(ctx, draft.ticket_ends_in)
        except ToolError:
            raise ActionNotSent("The note's ticket was not made in this call.") from None
        note = NewNote(
            request_id=ctx.request_id,
            customer_email=_customer(ctx),
            ticket_id=ticket.ticket_id,
            text=draft.note,
        )
        try:
            return NoteAdded.of(await system.add_note(note))
        except TicketRefused as error:
            raise _rejected(error) from error

    if system.can_find:

        @noted.lookup
        async def found(ctx: ActionContext, request_id: str) -> NoteAdded | None:
            ref = await system.find(request_id, customer_email=_customer(ctx))
            return None if ref is None else NoteAdded.of(ref)

    return noted


def hand_off(system: TicketSystem) -> Action:
    """The action that passes the caller's request to support staff as a ticket on `system`,
    the call's conversation attached (the module's docstring)."""

    @action(
        name=HAND_OFF,
        description=HANDOFF_DESCRIPTION,
        read_back=lines.HANDOFF_READ_BACK,
        done=lines.HANDOFF_DONE,
        claims=lines.HANDOFF_CLAIMS,
        sending=lines.HANDOFF_SENDING,
        failed=lines.HANDOFF_FAILED,
        unknown=lines.HANDOFF_UNKNOWN,
        declined=lines.HANDOFF_DECLINED,
        validate=has_customer,
        max_per_call=HANDOFFS_PER_CALL,
    )
    async def handed(ctx: ActionContext, draft: HandoffDraft) -> TicketMade:
        ticket = NewTicket(
            request_id=ctx.request_id,
            customer_email=_customer(ctx),
            queue=QUEUE_OF[HANDOFF_TYPE],
            type=HANDOFF_TYPE,
            priority=DEFAULT_PRIORITY,
            summary=draft.summary,
            transcript=ctx.conversation,
        )
        try:
            return TicketMade.of(await system.create(ticket))
        except TicketRefused as error:
            raise _rejected(error) from error

    if system.can_find:

        @handed.lookup
        async def found(ctx: ActionContext, request_id: str) -> TicketMade | None:
            ref = await system.find(request_id, customer_email=_customer(ctx))
            return None if ref is None else TicketMade.of(ref)

    return handed
