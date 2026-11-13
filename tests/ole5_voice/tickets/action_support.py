"""What the tests of Ole5's actions and status tool share: the session's caller, a call's context
with a record of what it made, the outbox as a fake (`past_actions` is the library's, tested
there), and an action's context once the caller said yes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ole5_voice.customer import CUSTOMER_EMAIL
from ole5_voice.tickets.drafts import TicketMade
from ole5_voice.tickets.system import TicketRef
from t2_agentic_voice import (
    ActionContext,
    CallContext,
    Caller,
    ConversationLine,
    HeardConsent,
    RecordedAction,
)

from tests.ole5_voice.tickets.ticket_support import CUSTOMER


def caller(email: str | None = CUSTOMER) -> Caller:
    """The session's caller, as the token route mints it: the owner, as `email`'s customer
    (none when None, a dev caller)."""
    attributes = {} if email is None else {CUSTOMER_EMAIL: email}
    return Caller(subject="owner", attributes=attributes)


def recorded(action: str, ref: TicketRef, request_id: str = "req-made") -> RecordedAction:
    """`action`'s entry in a record or the outbox, for the ticket `ref` names."""
    return RecordedAction(
        action=action,
        request_id=request_id,
        result=TicketMade.of(ref).model_dump(mode="json"),
    )


class PastContext(CallContext):
    """A call's context whose outbox is `rows`: `past_actions` gives those of an action, in
    order, as the library's would for this caller."""

    rows: tuple[RecordedAction, ...] = ()

    async def past_actions(self, action: str) -> tuple[RecordedAction, ...]:
        return tuple(row for row in self.rows if row.action == action)


def call_context(
    *,
    record: Sequence[RecordedAction] = (),
    past: Sequence[RecordedAction] = (),
    email: str | None = CUSTOMER,
    language: Any = "en",
) -> PastContext:
    """A call of `email`'s customer whose record holds `record` and whose outbox holds `past`."""
    return PastContext(
        caller=caller(email),
        call_id="call-1",
        language=language,
        record=tuple(record),
        rows=tuple(past),
    )


def action_context(
    request_id: str = "req-1",
    *,
    record: Sequence[RecordedAction] = (),
    conversation: Sequence[ConversationLine] = (),
    email: str | None = CUSTOMER,
) -> ActionContext:
    """An action's context once the caller said yes, for `email`'s customer."""
    return ActionContext(
        caller=caller(email),
        call_id="call-1",
        language="en",
        record=tuple(record),
        request_id=request_id,
        consent=HeardConsent(words="yes, send it", source="typed", speech_at=None),
        conversation=tuple(conversation),
    )
