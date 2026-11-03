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
NOW = EXPIRES - timedelta(seconds=90)  # the store's clock


class _Used:
    """A used-token store in a dict, on a clock of its own (`now`): as the port's `use` says, a
    token whose last instant is not after it is never recorded."""

    def __init__(self, now: datetime = NOW) -> None:
        self.used: dict[str, datetime] = {}
        self.now = now
        self.closed = False

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        if expires_at <= self.now or token_id in self.used:
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


def test_a_token_past_its_last_instant_is_never_a_first_use() -> None:
    """The port's `use`: an `expires_at` that is not after the store's now gives False and
    records nothing, so a join decoded just before the token's last instant, which reaches the
    store just after it, starts no call."""
    store = _Used()
    for late in (NOW - timedelta(milliseconds=1), NOW):
        assert not asyncio.run(store.use("late", expires_at=late))
    assert store.used == {}
    assert asyncio.run(store.use("late", expires_at=NOW + timedelta(milliseconds=1)))


def test_a_join_context_is_frozen() -> None:
    join = JoinContext(env="test", client_host=None, used_tokens=_Used())
    with pytest.raises(dataclasses.FrozenInstanceError):
        join.env = "dev"  # type: ignore[misc]
    assert asyncio.run(join.used_tokens.use("j", expires_at=EXPIRES + timedelta(seconds=60)))
