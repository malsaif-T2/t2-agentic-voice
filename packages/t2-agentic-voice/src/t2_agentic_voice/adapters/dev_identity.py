"""The dev caller (the design's 4.2 and 6.5): an `IdentityVerifier` for `t2v dev` and a team's own
machine. Public through the `identity` facade.

It serves only `env` dev and only loopback clients: any other `env` is refused before it reads
the client's address, and any other client after, each with a `JoinRejected`. A loopback
client is one whose address is in 127.0.0.0/8 or is ::1 (an IPv4 loopback address written in
IPv6, `::ffff:127.0.0.1`, too); an unknown address (None) or a name is refused. It always
returns `Caller(subject="dev")` and `Consent(version=None, record_audio=False)`, a plain
consent, so a dev call is never recorded (invariant 8). The token is never read.
"""

from __future__ import annotations

import ipaddress

from t2_agentic_voice.core.errors import JoinRejected
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.ports.identity import JoinContext

DEV_SUBJECT = "dev"


def is_loopback(host: str | None) -> bool:
    """Whether `host` is a loopback address: in 127.0.0.0/8, ::1, or an IPv4 loopback address
    mapped into IPv6. None, a name or anything that is no address is not."""
    if host is None:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


class DevIdentity:
    """A fixed dev caller, for `env` dev and loopback clients only."""

    async def verify(self, token: str, *, join: JoinContext) -> tuple[Caller, Consent]:
        """The dev caller and its consent, whatever `token` holds (the `IdentityVerifier` port's
        `verify`); JoinRejected outside `env` dev or from a client that is not on loopback."""
        if join.env != "dev":
            raise JoinRejected(
                "The dev caller joins only a server whose env is dev.",
                details={"reason": "not_dev"},
            )
        if not is_loopback(join.client_host):
            raise JoinRejected(
                "The dev caller joins only from this machine.", details={"reason": "not_loopback"}
            )
        return Caller(subject=DEV_SUBJECT), Consent(version=None, record_audio=False)
