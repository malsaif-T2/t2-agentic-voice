"""Per-call TURN credentials (adapters/turn_credentials.py): a stub until the deployment's plan
builds them and replaces this file's stub test with its own (coturn's scheme on a fixed vector;
TD-048)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from t2_agentic_voice.adapters.turn_credentials import TurnCredentials, turn_credentials

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_turn_credentials_are_a_stub_until_the_deployment() -> None:
    secret = SecretStr("made-up-turn-secret-of-at-least-32-bytes")
    with pytest.raises(NotImplementedError, match="TD-048"):
        turn_credentials(secret, call_id="call-1", ttl_s=3600, now=NOW)
    password = "made-up-turn-password"
    made = TurnCredentials(
        username="1793620800:call-1", password=SecretStr(password), expires_at=NOW
    )
    assert password not in repr(made)
