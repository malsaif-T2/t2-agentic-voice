"""Signed join tokens (the design's 6.5): compact JWTs, HS256 only, minted by a team's website or
app and verified once, at join; an `IdentityVerifier`. Built by plan 003's Track C; until then a
stub. Public through the `identity` facade.

The claims are `sub`, `name`, `locale`, `attrs`, `consent` (`version`, `record_audio`), `jti`,
`iat` and `exp`, with a `kid` header; a token is signed, not encrypted, so none holds a secret.
Any listed key verifies, and `current_kid` signs. Each key is at least 32 bytes (RFC 7518, 3.2),
also refused at verify; PyJWT's minimum key length is on for encode and decode, through one
`jwt.PyJWT(options={"enforce_minimum_key_length": True})`, `algorithm="HS256"` given and
`algorithms=["HS256"]` required, so a token cannot choose its own algorithm (plan 003's appendix,
"Changes to the plan's interfaces", item 25). A token lives `join.ttl_s` (120 s at most), is
used once (the runtime's `UsedTokens`), and its claims are parsed strictly: `record_audio` a JSON
boolean, the consent version a bounded string. Every refusal is a `JoinRejected` that holds no
value of the token. Only this module builds a `SignedConsent` (`[[restricted]]`): the consent a
verified token carried, the only one that can let a call be recorded (invariant 8).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import SecretStr

from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.base import PREFIX
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.domain.ports.identity import JoinContext

_STUB = "SignedJoinTokens is built by plan 003's Track C"


class SignedJoinTokens:
    """Mints and verifies join tokens with `keys` (key ID to secret), signing with
    `current_kid`'s (None: this instance only verifies), each living `ttl_s`, their times
    allowed `max_clock_skew_s` off this machine's clock. Built with no IO."""

    def __init__(
        self,
        *,
        keys: Mapping[str, SecretStr],
        current_kid: str | None = None,
        ttl_s: int = 60,
        max_clock_skew_s: int = 30,
    ) -> None:
        raise NotImplementedError(_STUB)

    @classmethod
    def from_settings(cls, join: JoinSettings, *, prefix: str = PREFIX) -> SignedJoinTokens:
        """The tokens the `join` settings describe: its keys (inline or from `join.keys_file`,
        whose errors name its variable under `prefix`), `current_kid`, `ttl_s` and
        `max_clock_skew_s` (the design's 4.5)."""
        raise NotImplementedError(_STUB)

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        """A new token for `caller`, carrying `consent`, signed with `current_kid`'s key: the
        reference implementation a team's own minting follows (the design's 6.5)."""
        raise NotImplementedError(_STUB)

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        """The caller and the consent `token` carries (the `IdentityVerifier` port's `verify`),
        the consent a `SignedConsent`; JoinRejected otherwise."""
        raise NotImplementedError(_STUB)
