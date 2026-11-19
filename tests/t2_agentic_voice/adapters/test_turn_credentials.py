"""Per-call TURN credentials (adapters/turn_credentials.py, D-128): coturn's REST scheme on a
fixed vector, the user name the expiry and the call's ID, the password the base64 HMAC-SHA1 of
it under the shared secret, and a password that never shows in a repr."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr
from t2_agentic_voice.adapters.turn_credentials import turn_credentials

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
SECRET = "made-up-turn-secret-of-at-least-32-bytes"


def test_the_credentials_follow_coturns_rest_scheme() -> None:
    made = turn_credentials(SecretStr(SECRET), call_id="call-1", ttl_s=3600, now=NOW)
    expiry = int((NOW + timedelta(seconds=3600)).timestamp())
    assert made.username == f"{expiry}:call-1" == "1793624400:call-1"
    mac = hmac.new(SECRET.encode(), made.username.encode(), hashlib.sha1).digest()
    assert made.password.get_secret_value() == base64.b64encode(mac).decode()
    assert made.expires_at == NOW + timedelta(seconds=3600)
    assert made.password.get_secret_value() not in repr(made)
