"""The dev caller (the design's 4.2 and 6.5): an `IdentityVerifier` for `t2v dev` and a team's own
machine. Built by plan 003's Track C; until then a stub. Public through the `identity` facade.

It serves only `env` dev and only loopback clients: any other `env` is refused before it reads
the client's address, and any other client after, each with a `JoinRejected`. It always returns
`Caller(subject="dev")` and `Consent(version=None, record_audio=False)`, a plain consent, so a
dev call is never recorded (invariant 8).
"""

from __future__ import annotations

from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.identity import JoinContext

_STUB = "DevIdentity is built by plan 003's Track C"


class DevIdentity:
    """A fixed dev caller, for `env` dev and loopback clients only."""

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        """The dev caller and its consent, whatever `token` holds (the `IdentityVerifier` port's
        `verify`); JoinRejected outside `env` dev or from a client that is not on loopback."""
        raise NotImplementedError(_STUB)
