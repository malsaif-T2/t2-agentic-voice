"""The dev caller (adapters/dev_identity.py): `env` dev and loopback clients only, any other `env`
refused before the client's address is read, and a consent that never records."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from t2_agentic_voice.adapters.dev_identity import DevIdentity, is_loopback
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens
from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.errors import JoinRejected
from t2_agentic_voice.core.identity import Caller, Consent, allows_recording
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext

LOOPBACK = ["127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1"]
ELSEWHERE = [
    None,
    "",
    "192.168.1.20",
    "10.0.0.1",
    "0.0.0.0",  # noqa: S104 - an address the test refuses, never bound
    "::",
    "::ffff:10.0.0.1",
    "2001:db8::1",
    "localhost",
    "testclient",
]


def _join(env: Environment, host: str | None) -> JoinContext:
    return JoinContext(env=env, client_host=host, used_tokens=MemoryUsedTokens())


class _Unread:
    """A join whose client address fails the test if it is read."""

    def __init__(self, env: Environment) -> None:
        self.env = env
        self.used_tokens = MemoryUsedTokens()

    @property
    def client_host(self) -> str:
        raise AssertionError("the client's address was read")


@pytest.mark.parametrize("host", LOOPBACK)
def test_a_loopback_client_in_dev_is_the_dev_caller_who_never_records(host: str) -> None:
    verifier: IdentityVerifier = DevIdentity()  # mypy checks the port's shape
    for token in ["dev", "made.up.token", ""]:
        caller, consent = asyncio.run(verifier.verify(token, join=_join("dev", host)))
        assert caller == Caller(subject="dev")
        assert consent == Consent(version=None, record_audio=False)
        assert type(consent) is Consent
        assert allows_recording(consent) is False


@pytest.mark.parametrize("env", ["test", "staging", "prod"])
def test_any_env_but_dev_is_refused_before_the_address_is_read(env: Environment) -> None:
    join = cast(JoinContext, _Unread(env))
    with pytest.raises(JoinRejected, match="only a server whose env is dev") as refused:
        asyncio.run(DevIdentity().verify("dev", join=join))
    assert refused.value.details == {"reason": "not_dev"}
    assert refused.value.__cause__ is None


@pytest.mark.parametrize("host", ELSEWHERE)
def test_a_client_that_is_not_on_loopback_is_refused_in_dev(host: str | None) -> None:
    with pytest.raises(JoinRejected, match="only from this machine") as refused:
        asyncio.run(DevIdentity().verify("dev", join=_join("dev", host)))
    assert refused.value.details == {"reason": "not_loopback"}
    if host:
        assert host not in str(refused.value)


def test_loopback_is_an_address_never_a_name() -> None:
    assert all(is_loopback(host) for host in LOOPBACK)
    assert not any(is_loopback(host) for host in ELSEWHERE)
