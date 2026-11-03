"""The dev caller (adapters/dev_identity.py). Plan 003's Track C builds it and replaces this file's
stub test with its own (any `env` but dev refused before the client's address is read)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.adapters.dev_identity import DevIdentity
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext


def test_the_dev_caller_is_a_stub_until_track_c() -> None:
    verifier: IdentityVerifier = DevIdentity()  # mypy checks the port's shape
    join = JoinContext(env="dev", client_host="127.0.0.1", used_tokens=MemoryUsedTokens())
    with pytest.raises(NotImplementedError, match="Track C"):
        asyncio.run(verifier.verify("dev", join=join))
