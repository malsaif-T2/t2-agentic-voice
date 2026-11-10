"""Ole5's ticket status (plan 007's Q4 and Q6): a read tool, `ticket_status`, whose results may
back up what the talker says of the tickets `create_ticket` and `hand_off` made (`reports_on`,
the design's 8.2, rule A).

The ticket system has no list of a customer's tickets, so the outbox is the list: only the
tickets made through the agent for this caller (`CallContext.past_actions`, scoped to the
verified caller), each read from the system with the session's customer (customer.py), bound
from the caller and never shown to the talker (docs/SECURITY.md, invariant 3). A ticket the
system does not hold for that customer is left out, so an outbox row of a customer the
settings named before shows nothing. A number the caller says is matched only among those
tickets, by its last digits, never looked up on its own; when one of theirs matches, the result
gives its last four digits back, so the talker says them first, and each ticket by its last four
digits only, never its whole number (Q6). Its summary, type, priority and status are the
caller's own ticket's. Digits that match none are not given back: a status result backs a claim
that a ticket was made (rule A), so another customer's number, or one never issued, must not be
in it (invariant 2); the talker may still say them back as the caller's own words (rule B).

A ticket system that fails is a ToolError the talker reads: it says it cannot check now.
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from t2_agentic_voice import CallContext, Tool, ToolError, from_caller, tool
from t2_agentic_voice.languages import normalize_digits

from ole5_voice.customer import CUSTOMER_FIELD
from ole5_voice.tickets.drafts import CREATE_TICKET, GROUP, HAND_OFF, MAKERS, made_in
from ole5_voice.tickets.system import TicketSystem, TicketSystemError
from ole5_voice.tickets.values import CLOSED, Priority, Status, TicketType

TICKET_STATUS: Final = "ticket_status"
# The most tickets one answer lists, the newest: a reply says each aloud.
LISTED: Final = 5
# The digits a ticket number has, the most a caller can say of one.
NUMBER_DIGITS: Final = 16
STATUS_DESCRIPTION: Final = (
    "Look up the caller's own tickets and their status: only the tickets made for this caller "
    "through this voice line, newest last. Call it when the caller asks about a ticket or a "
    "request they made. Give `number` only when the caller says a ticket number, with the "
    "digits they said; leave it out to hear all of their tickets."
)
_NUMBER_HELP: Final = (
    "The digits of a ticket number the caller said, all of them or the last four or more, as "
    "digits. Leave it out when they said none."
)
_SCOPE: Final = (
    "Only tickets made for this caller through this voice line are listed; any other ticket "
    "cannot be seen here. Say only the last four digits of a ticket's number."
)
_NONE_MATCH: Final = (
    "None of the caller's tickets made through this voice line ends in those digits. Tickets "
    "made any other way, or anyone else's, cannot be seen here, so say nothing of any."
)
_TOO_FEW: Final = "Ask the caller for at least the last four digits of the ticket's number."
_TOO_MANY: Final = "A ticket number has 16 digits; ask the caller to say it again."
_UNAVAILABLE: Final = (
    "The ticket system did not answer. Tell the caller you cannot check their tickets right now "
    "and that they can ask again shortly."
)


class SeenTicket(BaseModel):
    """One of the caller's tickets as the talker is told of it: the last four digits of its
    number, which action made it (`by`), its type, priority and status, whether it is closed,
    its summary and the day it was opened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ends_in: str
    by: Literal["create_ticket", "hand_off"]
    type: TicketType
    priority: Priority
    status: Status
    closed: bool
    summary: str
    opened_on: str


class StatusAnswer(BaseModel):
    """What `ticket_status` gives the talker: the caller's tickets (`LISTED` at most, newest
    last), how many there are in all, the last four digits of a number the caller said when one
    of their tickets ends in it (`asked_ends_in`, none otherwise), and how to read the answer
    (`note`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tickets: tuple[SeenTicket, ...]
    total: int
    asked_ends_in: str | None = None
    note: str


def said_digits(number: str) -> str:
    """The digits of a number the talker passed as the caller said it: Arabic-Indic digits and
    digit words read as the output guard reads them, anything else dropped."""
    return re.sub("[^0-9]", "", normalize_digits(number))


def ticket_status(system: TicketSystem) -> Tool:
    """The status tool over `system` (the module's docstring)."""

    @tool(
        name=TICKET_STATUS,
        description=STATUS_DESCRIPTION,
        bind={"customer": from_caller(CUSTOMER_FIELD)},
        reports_on=MAKERS,
    )
    async def status(
        ctx: CallContext,
        customer: str,
        number: Annotated[str | None, Field(max_length=64, description=_NUMBER_HELP)] = None,
    ) -> StatusAnswer:
        digits = None if number is None else said_digits(number)
        if digits is not None and len(digits) < GROUP:
            raise ToolError(_TOO_FEW)
        if digits is not None and len(digits) > NUMBER_DIGITS:
            raise ToolError(_TOO_MANY)
        made = [
            pair
            for name in (CREATE_TICKET, HAND_OFF)
            for pair in made_in(await ctx.past_actions(name))
        ]
        if digits is not None:
            made = [(by, ticket) for by, ticket in made if ticket.number.endswith(digits)]
        read = []
        for by, ticket in made:
            try:
                found = await system.get(ticket.ticket_id, customer_email=customer)
            except TicketSystemError:
                raise ToolError(_UNAVAILABLE) from None
            if found is not None and found.number == ticket.number:
                read.append((by, found))
        read.sort(key=lambda pair: pair[1].created_at)
        seen = [
            SeenTicket(
                ends_in=found.number[-GROUP:],
                by="hand_off" if by == HAND_OFF else "create_ticket",
                type=found.type,
                priority=found.priority,
                status=found.status,
                closed=found.status in CLOSED,
                summary=found.summary,
                opened_on=found.created_at.date().isoformat(),
            )
            for by, found in read
        ]
        return StatusAnswer(
            tickets=tuple(seen[-LISTED:]),
            total=len(seen),
            asked_ends_in=seen[-1].ends_in if digits is not None and seen else None,
            note=_NONE_MATCH if digits is not None and not seen else _SCOPE,
        )

    return status
