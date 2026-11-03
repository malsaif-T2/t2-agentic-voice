"""Signed join tokens (adapters/join_tokens.py). Plan 003's Track C builds them and replaces this
file's stub test with its own (invariant 7's adversarial cases)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.join_tokens import SignedJoinTokens
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext

KEY = SecretStr("made-up-join-key-of-at-least-32-bytes-0123")


def test_signed_join_tokens_are_a_stub_until_track_c() -> None:
    builds: list[Callable[[], object]] = [
        lambda: SignedJoinTokens(keys={"k1": KEY}, current_kid="k1"),
        lambda: SignedJoinTokens.from_settings(JoinSettings()),
    ]
    for build in builds:
        with pytest.raises(NotImplementedError, match="Track C"):
            build()
    stub = SignedJoinTokens.__new__(SignedJoinTokens)  # the methods' stubs
    verifier: IdentityVerifier = stub  # mypy checks the port's shape
    join = JoinContext(env="dev", client_host="127.0.0.1", used_tokens=MemoryUsedTokens())
    with pytest.raises(NotImplementedError, match="Track C"):
        stub.mint(Caller(subject="made-up"), consent=Consent(version=None, record_audio=False))
    with pytest.raises(NotImplementedError, match="Track C"):
        asyncio.run(verifier.verify("made.up.token", join=join))
