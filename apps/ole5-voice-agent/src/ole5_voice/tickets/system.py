"""The one small interface Ole5's actions and tools reach a ticket system through
(`TicketSystem`), its data and its errors.

Four calls: `create` a ticket, `get` one, `add_note` to one, and `find` the ticket a write made
by its request ID, a lookup a system may not have (`can_find`): the real one keeps no request
ID as far as anyone knows (plan 007, "What is known about the ticket system"). Every read and
note is scoped by the customer's email, which the caller of these calls takes from the session
(ole5_voice/customer.py), never from what was said in the call (docs/SECURITY.md, invariant 3):
a ticket of another customer is never returned, found or noted.

The mock (mock.py) implements it, and so will an adapter for the real system, in one file,
once someone has access (plan 007's Q2); no code here reaches a real ticket system. Every value
with a fixed set is one of values.py's (invariant 4). A summary, a note and the transcript are
call content: no error or log line holds one, nor an email (GP-19).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from t2_agentic_voice import ConversationLine, T2VoiceError

from ole5_voice.tickets.values import DEFAULT_PRIORITY, Priority, Queue, Status, TicketType

# A ticket number in the real shape: the date (YYYYMMDD), 82, a six-digit counter (plan 002).
NUMBER_PATTERN: Final = r"^[0-9]{8}82[0-9]{6}$"
# The longest summary (plan 007's Q5) and note a ticket takes, in characters.
MAX_SUMMARY_CHARS: Final = 200
MAX_NOTE_CHARS: Final = 1000

_FROZEN: Final = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
RequestId = Annotated[str, Field(min_length=1, max_length=128)]
Email = Annotated[str, Field(min_length=3, max_length=254, repr=False)]
TicketId = Annotated[str, Field(min_length=1, max_length=64)]
Number = Annotated[str, Field(pattern=NUMBER_PATTERN)]
Summary = Annotated[str, Field(min_length=1, max_length=MAX_SUMMARY_CHARS, repr=False)]


class TicketRef(BaseModel):
    """Which ticket: the system's own ID for it, and its number, the one said to the caller."""

    model_config = _FROZEN

    id: TicketId
    number: Number


class NewTicket(BaseModel):
    """A ticket to create: the write's `request_id`; the customer it is for, from the session;
    its queue, type and priority; the summary read back to the caller; and, for a handoff, what
    both sides said in the call (plan 007's Q7)."""

    model_config = _FROZEN

    request_id: RequestId
    customer_email: Email
    queue: Queue
    type: TicketType
    priority: Priority = DEFAULT_PRIORITY
    summary: Summary
    transcript: tuple[ConversationLine, ...] = ()


class NewNote(BaseModel):
    """A note to add to one of the customer's tickets: the write's `request_id`, the customer
    from the session, the ticket's ID and the note's text."""

    model_config = _FROZEN

    request_id: RequestId
    customer_email: Email
    ticket_id: TicketId
    text: Annotated[str, Field(min_length=1, max_length=MAX_NOTE_CHARS, repr=False)]


class Ticket(BaseModel):
    """A ticket as `get` reads it: its ID and number, queue, type, priority, status, summary,
    and when it was created, aware."""

    model_config = _FROZEN

    id: TicketId
    number: Number
    queue: Queue
    type: TicketType
    priority: Priority
    status: Status
    summary: Summary
    created_at: AwareDatetime


class TicketSystem(Protocol):
    """A ticket system, as the module says."""

    @property
    def can_find(self) -> bool:
        """Whether `find` can look a write up by its request ID."""
        ...

    async def create(self, ticket: NewTicket) -> TicketRef:
        """Create `ticket`: the new ticket's ID and number. TicketRefused when the system
        refused it (definitely not made); any other error, or no reply, may have made it."""
        ...

    async def get(self, ticket_id: str, *, customer_email: str) -> Ticket | None:
        """The ticket `ticket_id`, None when there is none or it is not `customer_email`'s."""
        ...

    async def add_note(self, note: NewNote) -> TicketRef:
        """Add `note` to its ticket: that ticket's ID and number. TicketRefused when the system
        refused it, the ticket not the customer's among the reasons."""
        ...

    async def find(self, request_id: str, *, customer_email: str) -> TicketRef | None:
        """The ticket the write `request_id` made, or added a note to, for `customer_email`;
        None when no write of theirs had it. LookupUnavailableError when `can_find` is
        False."""
        ...


# Why a ticket system refused a request, each in fixed words that hold none of its values.
RefusalReason = Literal["refused", "not_found", "full"]
_REFUSALS: Final[dict[RefusalReason, str]] = {
    "refused": "The ticket system refused the request.",
    "not_found": "The ticket system holds no such ticket for this customer.",
    "full": "The ticket system cannot number another ticket today.",
}


class TicketSystemError(T2VoiceError):
    """A ticket system's failure; its message holds no value of the request."""

    code = "ticket_system_error"


class TicketRefused(TicketSystemError):  # noqa: N818 - a refusal, as ActionRejected is
    """The system refused the request, for `reason`: definitely not done."""

    code = "ticket_refused"

    def __init__(self, reason: RefusalReason) -> None:
        super().__init__(_REFUSALS[reason], details={"reason": reason})
        self.reason: RefusalReason = reason


class TicketTimeoutError(TicketSystemError):
    """The system did not answer in time: the request may or may not have been done."""

    code = "ticket_timeout"

    def __init__(self) -> None:
        super().__init__("The ticket system did not answer in time.")


class LookupUnavailableError(TicketSystemError):
    """`find` was called on a system that cannot look a write up by its request ID."""

    code = "lookup_unavailable"

    def __init__(self) -> None:
        super().__init__("This ticket system cannot look a write up by its request ID.")
