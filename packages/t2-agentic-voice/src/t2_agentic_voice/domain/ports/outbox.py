"""The outbox port (the design's 6.4; docs/SECURITY.md, invariant 6): a durable store of every
write an action asks for, a row with its request ID written before the write. A write with no
reply is never repeated blindly: at start, rows left `sending` are looked up or flagged, never
sent again. The store also answers what a caller has done, across calls: the per-caller cap and
a status tool read it. The caps count only the writes that may have reached the system, never
one refused or never sent (`NOT_WRITTEN`).

A row holds call content (the draft, the result), so its text is logged at no level (invariant
8). Public through the `ports` facade, provisional. `SqliteOutbox` lives in `adapters` and
`MemoryOutbox`, which `testing` may use, in `actions`; the `stores` facade gives both.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from t2_agentic_voice.core.events import CallId

# Where a row stands: the write is under way or its reply never came; it `done`; the backend
# `rejected` it; it was `not_sent` (definitely not done); or it is `flagged` for a person to
# reconcile (no reply and no lookup hit).
OutboxState = Literal["sending", "done", "rejected", "not_sent", "flagged"]
# The rows the caps never count: a write the backend refused or that was never sent, definitely
# not done, so the caller may try again (the owner's ruling of 2026-11-10). Every other row
# (`sending`, `done`, `flagged`) may have reached the system, and counts.
NOT_WRITTEN: Final[tuple[OutboxState, ...]] = ("rejected", "not_sent")


class OutboxEntry(BaseModel):
    """One write: its `request_id`, unique; the call and the verified caller (`subject`) that
    asked for it; the `action`; the `draft_json` read back; where it stands (`state`), with a
    word or two saying why (`note`, never a value) and the real result (`result_json`) once it
    returned; and when it was written and last changed, aware."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    request_id: str = Field(min_length=1, max_length=128)
    call_id: CallId
    subject: str = Field(min_length=1)
    action: str = Field(min_length=1)
    draft_json: str = Field(min_length=2, repr=False)
    state: OutboxState = "sending"
    note: str | None = None
    result_json: str | None = Field(default=None, repr=False)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Outbox(Protocol):
    """The durable store of writes. Safe when two calls use it at once, one process per
    `storage.var_dir`, which the runtime's lock file holds."""

    async def add(self, entry: OutboxEntry) -> bool:
        """Write `entry`, durable before this returns: True the first time; False when its
        `request_id` is held already, writing nothing, so a write is never sent twice."""

    async def mark(
        self,
        request_id: str,
        *,
        state: OutboxState,
        note: str | None = None,
        result_json: str | None = None,
    ) -> None:
        """Move the row `request_id` to `state`, with its `note` and `result_json`."""

    async def get(self, request_id: str) -> OutboxEntry | None:
        """The row `request_id`, None when there is none."""

    async def entries(
        self,
        *,
        state: OutboxState | None = None,
        subject: str | None = None,
        action: str | None = None,
    ) -> tuple[OutboxEntry, ...]:
        """The rows that match every filter given, oldest first."""

    async def count(self, *, subject: str, action: str, since: datetime) -> int:
        """How many writes of `action` `subject` asked for since `since` that may have reached
        the system: every row but one `rejected` or `not_sent` (`NOT_WRITTEN`). The per-caller
        cap reads it."""

    async def aclose(self) -> None:
        """Close what the store holds open; one that holds none returns at once."""
