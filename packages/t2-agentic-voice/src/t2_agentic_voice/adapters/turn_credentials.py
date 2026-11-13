"""Per-call TURN credentials (the design's 11): minted from the TURN service's shared secret by
coturn's REST scheme (its `use-auth-secret`), for `/join` to return with the ICE servers. A stub
until the deployment's plan builds it (TD-048): `/join` mints none.

The user name is `<expiry>:<call ID>`, the expiry in Unix seconds, so it holds no claim of the
join token (no `sub`, no `name`); the password is the HMAC of the user name under the shared
secret, in base64, as coturn checks it; both live `server.turn_ttl_s` (3600 s by default, refused
above 86400). The secret, at least 32 bytes, and each password are `SecretStr`s that reach no
log, trace, event or error.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, SecretStr

from t2_agentic_voice.core.events import CallId

_STUB = "TURN credentials are not built: the deployment's plan builds them (TD-048)"


class TurnCredentials(BaseModel):
    """One call's TURN user name and password, and when they expire."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    username: str
    password: SecretStr
    expires_at: AwareDatetime


def turn_credentials(
    secret: SecretStr, *, call_id: CallId, ttl_s: int, now: datetime
) -> TurnCredentials:
    """The credentials of call `call_id`, valid `ttl_s` from `now` (an aware time), minted with
    the shared `secret`."""
    raise NotImplementedError(_STUB)
