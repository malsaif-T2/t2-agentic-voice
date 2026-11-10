"""The outbox on SQLite (domain/ports/outbox.py), kept under `storage.var_dir` in its own file, on
the shape of adapters/used_tokens.py. `INSERT OR IGNORE` on the request ID is what makes a write
never go twice, and a row is durable before `add` returns.

Plan 007's Track B fills this.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Self

from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

_TRACK = "plan 007's Track B fills SqliteOutbox"


class SqliteOutbox:
    """Every write of one agent, in a SQLite file under its `var_dir` folder."""

    @classmethod
    async def open(cls, path: Path) -> Self:
        """The store kept in the file `path`, created when absent."""
        raise NotImplementedError(f"{_TRACK} ({path.name})")

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
