"""The used-token stores (the design's 6.5): the join tokens already used, each by its `jti`, so a
token starts one call only; `UsedTokens`. Built by plan 003's Track C; until then stubs. Public
through the `stores` facade (provisional).

`SqliteUsedTokens` keeps them in a SQLite file under `storage.var_dir`, across restarts, and
gives exactly one of two joins that use one token at once its True, from two threads too; only
`adapters` imports `sqlite3` (`[[owners]]`). A row is kept at least until its `expires_at`, the
last instant any verifier could still accept its token (the token's `exp` plus
`MAX_CLOCK_SKEW_S`, the bound on `join.max_clock_skew_s`, as `SignedJoinTokens` passes it), and
is pruned only after that. `use` reads the store's own clock, and gives False for an
`expires_at` that is not after its now, recording nothing. One process per `var_dir` holds the
file (the runtime's lock file). `MemoryUsedTokens` keeps them in memory only, for tests and a
dev machine. Track C's tests of each store: a row pruned once its `expires_at` has passed, and
kept while it has not; `use` with an `expires_at` a millisecond before the store's now gives
False and records nothing, so the same ID given later with a later `expires_at` gets True; and
a token used once, then given again twice with its `expires_at`, the store's clock set a
millisecond before that instant and then a millisecond after it, the row pruned between,
gets False both times.
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
