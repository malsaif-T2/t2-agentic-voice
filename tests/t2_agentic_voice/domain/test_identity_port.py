"""The identity port (the design's 6.5): a verifier and a used-token store that implement it, and
what the runtime hands a verifier at each join."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from t2_agentic_voice.core.errors import JoinRejected
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext, UsedTokens

EXPIRES = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class _Used:
    """A used-token store in a set."""

    def __init__(self) -> None:
        self.used: dict[str, datetime] = {}
        self.closed = False

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        if token_id in self.used:
            return False
        self.used[token_id] = expires_at
        return True

    async def aclose(self) -> None:
        self.closed = True


class _Named:
    """A verifier whose token is the caller's subject, used once, served in dev only."""

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        if join.env != "dev":
            raise JoinRejected("This join is not served here.")
        if not await join.used_tokens.use(token, expires_at=EXPIRES):
            raise JoinRejected("This join token was used before.")
        return Caller(subject=token), Consent(version=None, record_audio=False)


def test_a_verifier_and_a_store_implement_the_port() -> None:
    store = _Used()
    used: UsedTokens = store
    verifier: IdentityVerifier = _Named()
    join = JoinContext(env="dev", client_host="127.0.0.1", used_tokens=used)
    caller, consent = asyncio.run(verifier.verify("e-1", join=join))
    assert (caller.subject, consent) == ("e-1", Consent(version=None, record_audio=False))
    assert store.used == {"e-1": EXPIRES}
    with pytest.raises(JoinRejected, match="used before"):
        asyncio.run(verifier.verify("e-1", join=join))
    with pytest.raises(JoinRejected, match="not served"):
        asyncio.run(verifier.verify("e-2", join=dataclasses.replace(join, env="prod")))
    asyncio.run(used.aclose())
    assert store.closed


def test_a_join_context_is_frozen() -> None:
    join = JoinContext(env="test", client_host=None, used_tokens=_Used())
    with pytest.raises(dataclasses.FrozenInstanceError):
        join.env = "dev"  # type: ignore[misc]
    assert asyncio.run(join.used_tokens.use("j", expires_at=EXPIRES + timedelta(seconds=60)))
