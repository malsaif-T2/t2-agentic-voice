"""The outbox in memory (domain/ports/outbox.py): what a test and a `TextCall` use. It sits in
`actions`, not `adapters`, since `testing` may not import `adapters` (harness.toml [layers]);
the `stores` facade gives it beside `SqliteOutbox`.

Plan 007's Track B fills this.
"""

from __future__ import annotations

from datetime import datetime

from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

_TRACK = "plan 007's Track B fills MemoryOutbox"


class MemoryOutbox:
    """Every write of one process, in memory."""

    async def add(self, entry: OutboxEntry) -> bool:
        raise NotImplementedError(f"{_TRACK} ({entry.action})")

    async def mark(
        self,
        request_id: str,
        *,
        state: OutboxState,
        note: str | None = None,
        result_json: str | None = None,
    ) -> None:
        raise NotImplementedError(f"{_TRACK} ({state})")

    async def get(self, request_id: str) -> OutboxEntry | None:
        raise NotImplementedError(_TRACK)

    async def entries(
        self,
        *,
        state: OutboxState | None = None,
        subject: str | None = None,
        action: str | None = None,
    ) -> tuple[OutboxEntry, ...]:
        raise NotImplementedError(_TRACK)

    async def count(self, *, subject: str, action: str, since: datetime) -> int:
        raise NotImplementedError(f"{_TRACK} ({since})")

    async def aclose(self) -> None:
        raise NotImplementedError(_TRACK)
