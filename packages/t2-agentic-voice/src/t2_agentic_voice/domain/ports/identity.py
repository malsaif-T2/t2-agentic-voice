"""The identity port, as the design's 6.5 gives it: who is calling, verified once, at join, before
the call's offer is answered; and the store of join tokens already used, so a token starts one
call only.

`VoiceRuntime(identity=...)` takes one `IdentityVerifier`: `SignedJoinTokens`, which verifies
the compact JWTs a team's website or app mints, or `DevIdentity`, a fixed dev caller for `env`
dev and loopback clients only. A verifier is built in the team's code, with no IO, before the
runtime starts, while the used-token store is the runtime's, opened under `storage.var_dir` at
start and closed at stop; so the runtime hands the verifier what it knows of each join, the
store with it, in a `JoinContext`.

Every refusal is a `JoinRejected` whose message is safe to show the caller and holds no value of
the token (GP-19); the api layer turns it into its one error shape. Public through the `ports`
facade (the design's 5.1; `UsedTokens` provisional).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from t2_agentic_voice.core.config import Environment
from t2_agentic_voice.core.identity import Caller, Consent


class UsedTokens(Protocol):
    """The join tokens already used, each by its ID (a JWT's `jti`), each kept at least until
    the last instant its verifier could still accept the token, and shared by every call of the
    runtime (one process per `storage.var_dir`, which the runtime's lock file holds)."""

    async def use(self, token_id: str, *, expires_at: datetime) -> bool:
        """Record `token_id` as used, kept at least until `expires_at` (an aware time): True the
        first time, False when it was used before, the second use being refused. Safe when two
        joins use the same token at once: exactly one gets True. `expires_at` is the last
        instant the verifier could still accept the token: its `exp` plus the verifier's
        clock-skew allowance (`join.max_clock_skew_s`), never its `exp` alone, since a store
        that forgot the token at `exp` would let it start a second call within the
        allowance."""

    async def aclose(self) -> None:
        """Close what the store holds open (a database connection); a store that holds none
        returns at once. Called once, when the runtime stops."""


@dataclass(frozen=True)
class JoinContext:
    """What the runtime knows of one join, beside its token: the settings' `env`; the client's
    address as the server saw it (the connection's peer, or the address a trusted proxy
    forwarded; None when the server cannot tell); and the runtime's used-token store."""

    env: Environment
    client_host: str | None
    used_tokens: UsedTokens


class IdentityVerifier(Protocol):
    """An identity source behind the port: it turns a join token into the call's `Caller` and
    `Consent`, once per call."""

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        """The caller `token` proves and the consent it carries. Raises `JoinRejected` for every
        token or join it refuses (malformed, expired, used before, signed with a key it does
        not list, or a join it does not serve), holding no value of the token."""
