"""The used-token stores (adapters/used_tokens.py). Plan 003's Track C builds them and replaces
this file's stub test with its own (two threads at once, and after a restart)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens, SqliteUsedTokens
from t2_agentic_voice.domain.ports.identity import UsedTokens

EXPIRES = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_the_used_token_stores_are_stubs_until_track_c(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="Track C"):
        asyncio.run(SqliteUsedTokens.open(tmp_path / "used_tokens.db"))
    sqlite = SqliteUsedTokens.__new__(SqliteUsedTokens)  # the methods' stubs, past `open`'s
    stores: list[UsedTokens] = [sqlite, MemoryUsedTokens()]  # mypy checks the port's shape
    for store in stores:
        with pytest.raises(NotImplementedError, match="Track C"):
            asyncio.run(store.use("made-up", expires_at=EXPIRES))
        with pytest.raises(NotImplementedError, match="Track C"):
            asyncio.run(store.aclose())
