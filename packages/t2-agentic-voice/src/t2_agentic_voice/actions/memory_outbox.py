"""The outbox in memory (domain/ports/outbox.py): what a test and a `TextCall` use. It sits in
`actions`, not `adapters`, since `testing` may not import `adapters` (harness.toml [layers]);
the `stores` facade gives it beside `SqliteOutbox`.

It keeps the port's rules as `SqliteOutbox` does: `add` holds a request ID once and answers
False for it again, writing nothing; `mark` refuses a request ID it does not hold (LookupError,
naming no value); rows come oldest first, by `created_at`, then the order they were added; and
`count` refuses a naive `since`. A row's `updated_at` is the store's clock, `datetime.now(UTC)`
unless a test gives its own (`_now`). Gone when the process ends.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

# What `mark` says of a request ID the store does not hold, never the ID itself.
NO_ROW = "The outbox holds no row of that request ID."


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(since: datetime) -> datetime:
    """`since` when it is an aware time; a naive one is refused, since it names no instant."""
    if since.utcoffset() is None:
        raise ValueError("since must be an aware time (with a time zone), as UTC is")
    return since


class MemoryOutbox:
    """Every write of one process, in memory."""

    def __init__(self, *, _now: Callable[[], datetime] = _utc_now) -> None:
        self._now = _now
        self._rows: dict[str, OutboxEntry] = {}
        self._lock = threading.Lock()

    async def add(self, entry: OutboxEntry) -> bool:
        """Hold `entry` (the `Outbox` port's `add`): True the first time."""
        with self._lock:
            if entry.request_id in self._rows:
                return False
            self._rows[entry.request_id] = entry
            return True

    async def mark(
        self,
        request_id: str,
        *,
        state: OutboxState,
        note: str | None = None,
        result_json: str | None = None,
    ) -> None:
        """Move the row `request_id` to `state` (the `Outbox` port's `mark`), its result kept
        when none is given."""
        with self._lock:
            row = self._rows.get(request_id)
            if row is None:
                raise LookupError(NO_ROW)
            changed = {**row.model_dump(), "state": state, "note": note, "updated_at": self._now()}
            if result_json is not None:
                changed["result_json"] = result_json
            self._rows[request_id] = OutboxEntry.model_validate(changed)

    async def get(self, request_id: str) -> OutboxEntry | None:
        """The row `request_id`, None when there is none."""
        with self._lock:
            return self._rows.get(request_id)

    async def entries(
        self,
        *,
        state: OutboxState | None = None,
        subject: str | None = None,
        action: str | None = None,
    ) -> tuple[OutboxEntry, ...]:
        """The rows that match every filter given, oldest first."""
        with self._lock:
            rows = list(self._rows.values())
        kept = [
            row
            for row in rows
            if (state is None or row.state == state)
            and (subject is None or row.subject == subject)
            and (action is None or row.action == action)
        ]
        return tuple(sorted(kept, key=lambda row: row.created_at))

    async def count(self, *, subject: str, action: str, since: datetime) -> int:
        """How many writes of `action` `subject` asked for since `since`."""
        _aware(since)
        rows = await self.entries(subject=subject, action=action)
        return sum(1 for row in rows if row.created_at >= since)

    async def aclose(self) -> None:
        """Nothing to close."""
