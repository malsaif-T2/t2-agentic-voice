"""The ICE servers a call is given at join (`call_ice_servers`), each TURN server with the call's
own short-lived credentials (the owner, 2026-11-19: "It must work over the internet"; D-128).

A call's audio is WebRTC, UDP between the browser and the server. Over the internet a browser
behind a strict NAT or a firewall that lets only web traffic out cannot reach the server
directly; a TURN server relays the call's media for it, over UDP, TCP or TLS on port 443
(`turns:`), which passes wherever HTTPS does. The TURN server checks each call's credentials
with the secret it shares with this server (`server.turn_secret`), coturn's `use-auth-secret`
(adapters/turn_credentials.py). A STUN server, and a TURN server while no secret is set, is given
as it is, with no credentials. The browser gets them in `/join`'s answer; the server's own peer
is given the STUN servers alone (voice/calls.py), since it answers the browser's candidates, a
relay's among them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import SecretStr

from t2_agentic_voice.adapters.turn_credentials import turn_credentials
from t2_agentic_voice.api.protocol import IceServer
from t2_agentic_voice.core.settings.server import ServerSettings

__all__ = ["call_ice_servers", "is_turn"]


def is_turn(url: str) -> bool:
    """Whether `url` names a TURN server (`turn:` or `turns:`)."""
    return url.startswith(("turn:", "turns:"))


def call_ice_servers(
    server: ServerSettings, call_id: str, now: datetime, secret: SecretStr | None
) -> tuple[IceServer, ...]:
    """The ICE servers of `call_id`, joined at `now` (an aware time), each TURN server with the
    call's credentials under `secret` when one is set (the module's docstring)."""
    made = (
        None
        if secret is None
        else turn_credentials(secret, call_id=call_id, ttl_s=server.turn_ttl_s, now=now)
    )
    return tuple(
        IceServer(urls=(url,), username=made.username, credential=made.password)
        if made is not None and is_turn(url)
        else IceServer(urls=(url,))
        for url in server.ice_servers
    )
