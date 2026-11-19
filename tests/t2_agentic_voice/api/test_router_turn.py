"""`/join`'s ICE servers with each call's own TURN credentials (D-128)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
from pathlib import Path

import pytest
from pydantic import SecretStr
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.t2_agentic_voice.api.runtime_support import (
    TOKEN,
    Harness,
    dev_settings,
    post,
    serving,
)

pytestmark = pytest.mark.usefixtures("patched_stores")


def test_a_join_gives_each_turn_server_the_calls_own_credentials(tmp_path: Path) -> None:
    """D-128: with `server.turn_secret` set, each TURN URL comes with the call's short-lived
    credentials (coturn's use-auth-secret: expiry:call ID, base64 HMAC-SHA1), STUN with none."""
    secret = "a-made-up-turn-secret-of-at-least-32-bytes"
    servers = ServerSettings(
        ice_servers=("stun:stun.example.test:3478", "turns:turn.example.test:443"),
        turn_secret=SecretStr(secret),
        turn_ttl_s=600,
    )
    harness = Harness(dev_settings(tmp_path, server=servers))

    async def scene() -> None:
        before = int(time.time())
        async with serving(harness.app()) as http:
            answer = await post(http, "/join", {"token": TOKEN, "protocol": 1})
        body = answer.json()
        stun, turn = body["ice_servers"]
        assert stun == {
            "urls": ["stun:stun.example.test:3478"],
            "username": None,
            "credential": None,
        }
        expiry, call_id = turn["username"].split(":")
        assert call_id == body["call_id"] and before + 600 <= int(expiry) <= int(time.time()) + 600
        mac = hmac.new(secret.encode(), turn["username"].encode(), hashlib.sha1).digest()
        assert turn["credential"] == base64.b64encode(mac).decode()

    asyncio.run(scene())
