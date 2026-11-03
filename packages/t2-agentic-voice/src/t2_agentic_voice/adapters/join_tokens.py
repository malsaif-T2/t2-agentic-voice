"""Signed join tokens (the design's 6.5): compact JWTs, HS256 only, minted by a team's website or
app and verified once, at join; an `IdentityVerifier`. Public through the `identity` facade.

The claims are `sub`, `name`, `locale`, `attrs`, `consent` (`version`, `record_audio`), `jti`,
`iat` and `exp`, with a `kid` header; a token is signed, not encrypted, so none holds a secret.
Any listed key verifies, and `current_kid` signs. Each key is at least 32 bytes (RFC 7518, 3.2),
also refused at verify; PyJWT's minimum key length is on for encode and decode, through one
`jwt.PyJWT(options={"enforce_minimum_key_length": True})`, `algorithm="HS256"` given and
`algorithms=["HS256"]` required, so a token cannot choose its own algorithm (plan 003's appendix,
"Changes to the plan's interfaces", item 25). A token lives `join.ttl_s` (120 s at most), its
times allowed `max_clock_skew_s` off (60 s at most), is used once (the runtime's `UsedTokens`),
and its claims are parsed strictly: `record_audio` a JSON boolean, the consent version a bounded
string. A `ttl_s` above `MAX_TTL_S` or a `max_clock_skew_s` above `MAX_CLOCK_SKEW_S`
(core/settings/join.py) is a ConfigurationError at construction, as the settings refuse them.
`verify` records the token's `jti` with `expires_at` its `exp` plus `MAX_CLOCK_SKEW_S` (the
bound, never the configured `max_clock_skew_s`), the latest instant any verifier would still
take it, so the store never forgets a token a verifier would take again, after a restart with a
larger allowance included; and a token the store refuses, its last instant passed by the time
`use` runs, is refused as used before. Track C's replay tests: a token used once, the store
then pruned at the token's `exp`, and the token presented again before its `exp` plus the skew,
is refused as used before; and a token used through a store with a verifier allowed 30 s, the
store closed and opened again on the same file, then presented at its `exp` plus 45 s to a
verifier allowed 60 s, after the store pruned every row whose time had passed, is refused as
used before. Every refusal is a `JoinRejected` that holds no value of the token. Only this
module builds a `SignedConsent`, the consent a verified token carried, the only one that can
let a call be recorded (invariant 8): after the signature and every claim check pass, `verify`
builds it from the token's `consent` claim as
`SignedConsent.model_validate(claim, context=CONSENT_SEAL)` (core/identity.py), the only way one
is built. Only this module refers to `CONSENT_SEAL` (`[[restricted]]`), and it never stores the
seal, returns it or hands it on. Track C's tests: a verified token whose consent says
`record_audio` true gives a consent that `allows_recording` accepts; one that says false gives a
consent it refuses.

**The checks, in order.** The header must name a listed `kid`; then PyJWT checks the signature
with that key, HS256 only, and that every required claim is there (`sub`, `consent`, `jti`,
`iat` and `exp`; `name`, `locale` and `attrs` may be left out or null); then the claims are
parsed strictly, any other claim refused (`nbf`, `aud`, `iss`: a team that mints follows the
claims above); then the times, on this verifier's clock: a lifetime (`exp` minus `iat`) above
`ttl_s`, or none, is refused, as is an `iat` more than the allowance ahead of now or an `exp`
not after now less the allowance (PyJWT's own time checks are off, its clock being one no test
can set); then the caller and the consent are built, before the store is asked, so a token is
spent only by a join that can go on. A join refused before the store is asked spends nothing.
Each refusal's `details` give its reason (`malformed`, `unknown_key`, `signature`, `lifetime`,
`not_yet_valid`, `expired` or `used`) for the api layer's log, and none chains the error that
found it. The clock is `datetime.now(UTC)` unless a test gives its own (`_now`).
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final

import jwt
from jwt.types import Options
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from t2_agentic_voice.core.errors import ConfigurationError, JoinRejected
from t2_agentic_voice.core.identity import CONSENT_SEAL, Caller, Consent, SignedConsent
from t2_agentic_voice.core.settings.base import GENERATOR, PREFIX, secret, setting_name
from t2_agentic_voice.core.settings.join import MAX_CLOCK_SKEW_S, MAX_TTL_S, JoinSettings
from t2_agentic_voice.domain.ports.identity import JoinContext

ALGORITHM: Final = "HS256"
# PyJWT with its minimum key length on, for encode and decode alike (the appendix's item 25):
# module-level `jwt.encode` would use PyJWT's global object, which only warns.
_JWT: Final = jwt.PyJWT(options={"enforce_minimum_key_length": True})
REQUIRED_CLAIMS: Final = ("sub", "consent", "jti", "iat", "exp")
_DECODE: Final[Options] = {
    "require": list(REQUIRED_CLAIMS),
    "verify_exp": False,
    "verify_iat": False,
    "verify_nbf": False,
}
# A token's ID: 1 to 128 printable ASCII characters with no space (a UUID, a URL-safe random).
JTI_PATTERN = r"^[\x21-\x7e]{1,128}$"
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # core/settings/join.py's `KeyId`
_LAST_SECOND = 253402300799  # 9999-12-31T23:59:59Z, the last second a datetime holds
_Seconds = Annotated[int, Field(ge=0, le=_LAST_SECOND)]
_MESSAGES: Final = {
    "malformed": "This join token cannot be read: it is not a join token this server takes.",
    "unknown_key": "This join token names no key this server lists.",
    "signature": "This join token's signature does not verify.",
    "lifetime": "This join token lives longer than this server allows.",
    "not_yet_valid": "This join token is dated in the future.",
    "expired": "This join token has expired.",
    "used": "This join token was used before.",
}


def _utc_now() -> datetime:
    """The time now, aware, in UTC: a verifier's clock unless a test gives its own."""
    return datetime.now(UTC)


def _rejected(reason: str) -> JoinRejected:
    """The refusal for `reason`, in fixed words that hold no value of the token."""
    return JoinRejected(_MESSAGES[reason], details={"reason": reason})


class _Claims(BaseModel):
    """A token's claims, parsed strictly: exact JSON types and no other claim. The caller's own
    bounds are `Caller`'s, checked as it is built."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    sub: str
    name: str | None = None
    locale: str | None = None
    attrs: dict[str, str] | None = None
    consent: Consent
    jti: Annotated[str, Field(pattern=JTI_PATTERN)]
    iat: _Seconds
    exp: _Seconds


def _checked_keys(keys: Mapping[str, SecretStr]) -> dict[str, SecretStr]:
    """`keys` when each ID is a key ID and each secret at least 32 bytes of a key's characters;
    ConfigurationError otherwise, naming neither."""
    if not keys:
        raise ConfigurationError(
            "SignedJoinTokens was given no join key. FIX: pass keys={<key ID>: <secret>}, each "
            f"secret at least 32 bytes; make one with {GENERATOR}."
        )
    checked: dict[str, SecretStr] = {}
    for kid, value in keys.items():
        if not (isinstance(kid, str) and _KEY_ID.fullmatch(kid)):
            raise ConfigurationError(
                "A key ID given to SignedJoinTokens is not 1 to 64 letters, digits, '.', '_' or "
                "'-'. FIX: name each key so; the ID travels in every token's header."
            )
        checked[kid] = secret(value.get_secret_value(), "A join key given to SignedJoinTokens")
    return checked


def _bounded(value: int, name: str, least: int, most: int) -> int:
    """`value` when it is from `least` to `most`; ConfigurationError otherwise."""
    if not least <= value <= most:
        raise ConfigurationError(
            f"SignedJoinTokens' {name} must be from {least} to {most} seconds. FIX: pass a value "
            "in that range, as the join settings take it.",
            details={"setting": name},
        )
    return value


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
        _now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._keys = _checked_keys(keys)
        if current_kid is not None and current_kid not in self._keys:
            raise ConfigurationError(
                "SignedJoinTokens' current_kid names no key it was given. FIX: pass the ID of "
                "one of its keys, or None for an instance that only verifies.",
                details={"setting": "current_kid"},
            )
        self._current_kid = current_kid
        self._ttl_s = _bounded(ttl_s, "ttl_s", 1, MAX_TTL_S)
        self._skew_s = _bounded(max_clock_skew_s, "max_clock_skew_s", 0, MAX_CLOCK_SKEW_S)
        self._now = _now

    @classmethod
    def from_settings(cls, join: JoinSettings, *, prefix: str = PREFIX) -> SignedJoinTokens:
        """The tokens the `join` settings describe: its keys (inline or from `join.keys_file`,
        whose errors name its variable under `prefix`), `current_kid`, `ttl_s` and
        `max_clock_skew_s` (the design's 4.5)."""
        keys = join.resolved_keys(prefix)
        if not keys:
            setting = setting_name("join", "keys", prefix=prefix)
            file = setting_name("join", "keys_file", prefix=prefix)
            raise ConfigurationError(
                f"{setting} holds no join key, and {file} names no file that holds one. FIX: set "
                f'one of them to {{"<key ID>": "<secret>"}}, and make a secret with {GENERATOR}.',
                details={"setting": setting},
            )
        return cls(
            keys=keys,
            current_kid=join.current_kid,
            ttl_s=join.ttl_s,
            max_clock_skew_s=join.max_clock_skew_s,
        )

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        """A new token for `caller`, carrying `consent`, signed with `current_kid`'s key: the
        reference implementation a team's own minting follows (the design's 6.5)."""
        kid = self._current_kid
        if kid is None:
            raise ConfigurationError(
                "This SignedJoinTokens only verifies: it was built with no current_kid. FIX: "
                "pass current_kid, the ID of the key that signs, to mint tokens."
            )
        issued = int(self._now().timestamp())
        claims: dict[str, Any] = {
            "sub": caller.subject,
            "name": caller.display_name,
            "locale": caller.locale,
            "attrs": dict(caller.attributes) or None,
            "consent": {"version": consent.version, "record_audio": consent.record_audio},
            "jti": secrets.token_urlsafe(16),
            "iat": issued,
            "exp": issued + self._ttl_s,
        }
        payload = {claim: value for claim, value in claims.items() if value is not None}
        key = self._keys[kid].get_secret_value()
        return _JWT.encode(payload, key, algorithm=ALGORITHM, headers={"kid": kid})

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        """The caller and the consent `token` carries (the `IdentityVerifier` port's `verify`),
        the consent a `SignedConsent`; JoinRejected otherwise."""
        claims, caller = self._read(token)
        expires_at = datetime.fromtimestamp(claims.exp, UTC) + timedelta(seconds=MAX_CLOCK_SKEW_S)
        if not await join.used_tokens.use(claims.jti, expires_at=expires_at):
            raise _rejected("used")
        consent = SignedConsent.model_validate(claims.consent.model_dump(), context=CONSENT_SEAL)
        return caller, consent

    def _read(self, token: str) -> tuple[_Claims, Caller]:
        """The claims and the caller of `token`, its signature and times checked."""
        claims = self._decoded(token)
        now = self._now().timestamp()
        if not 0 < claims.exp - claims.iat <= self._ttl_s:
            raise _rejected("lifetime")
        if claims.iat > now + self._skew_s:
            raise _rejected("not_yet_valid")
        if claims.exp <= now - self._skew_s:
            raise _rejected("expired")
        try:
            caller = Caller(
                subject=claims.sub,
                display_name=claims.name,
                locale=claims.locale,
                attributes=claims.attrs or {},
            )
        except ValidationError:
            caller = None  # its errors are not chained
        if caller is None:
            raise _rejected("malformed")
        return claims, caller

    def _decoded(self, token: str) -> _Claims:
        """The claims of `token` once its header names a listed key and the signature verifies
        with it; each refusal chains nothing."""
        reason = "malformed"
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = self._keys.get(kid) if isinstance(kid, str) else None
            if key is not None:
                payload = _JWT.decode(
                    token, key.get_secret_value(), algorithms=[ALGORITHM], options=_DECODE
                )
                return _Claims.model_validate(payload)
            reason = "unknown_key"
        except (jwt.InvalidSignatureError, jwt.InvalidAlgorithmError, jwt.InvalidKeyError):
            reason = "signature"
        except (jwt.PyJWTError, ValidationError):
            reason = "malformed"
        raise _rejected(reason)
