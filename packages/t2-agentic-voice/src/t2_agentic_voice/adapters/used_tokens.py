"""The used-token stores (the design's 6.5): the join tokens already used, each by its `jti`, so a
token starts one call only; `UsedTokens`. Built by plan 003's Track C; until then stubs. Public
through the `stores` facade (provisional).

`SqliteUsedTokens` keeps them in a SQLite file under `storage.var_dir`, across restarts, and
gives exactly one of two joins that use one token at once its True, from two threads too; only
`adapters` imports `sqlite3` (`[[owners]]`). A row is kept at least until its token expires. One
process per `var_dir` holds the file (the runtime's lock file). `MemoryUsedTokens` keeps them in
memory only, for tests and a dev machine.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_STUB = "the used-token stores are built by plan 003's Track C"


class SqliteUsedTokens:
    """The used tokens of one runtime, in the SQLite file `open` was given."""

    @classmethod
    async def open(cls, path: Path) -> SqliteUsedTokens:
        """The store in the file at `path`, created with its folder when missing; called at the
        runtime's start. Close it with `aclose()`."""
        raise NotImplementedError(_STUB)

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used (the `UsedTokens` port's `use`): True the first time."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """Close the database connection."""
        raise NotImplementedError(_STUB)


class MemoryUsedTokens:
    """The used tokens in memory, gone when the process ends."""

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used (the `UsedTokens` port's `use`): True the first time."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """Nothing to close."""
        raise NotImplementedError(_STUB)
