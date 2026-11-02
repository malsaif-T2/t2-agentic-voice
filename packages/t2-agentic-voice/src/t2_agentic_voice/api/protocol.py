"""The HTTP bodies of `t2v/1` (the design's 5.5), after the router's prefix: `POST /join` takes a
join token and the client's protocol version, and answers the call's ID, its offer secret, the
ICE servers and the server's version; `POST /offer` takes the call's SDP offer and answers its
SDP answer; `PATCH /offer` takes trickled ICE candidates, an empty one marking their end
(plan 003's appendix, item 14). The data channel's messages are voice/protocol.py's.

A request body comes from the browser, which is not trusted: it is parsed strictly, with
exactly its fields, each of its JSON type, and every size bounded (the bounds are the agent's,
each well over what a browser sends). The offer secret is the call's alone: it rides in the
`OFFER_SECRET_HEADER` header or the body's `offer_secret`, never in a URL, which logs and
traces keep. The call ID is no credential (the design's 5.5), and a client never sends
Pipecat's `pc_id`, which `voice` keeps behind the call ID (the appendix, item 10).

A secret (the offer secret, the join token, a TURN password) is a `SecretStr` here, so no repr
or log line of a body shows it; a response reveals its own only as it is sent.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, field_serializer

from t2_agentic_voice.core.events import MAX_INDEX, CallId
from t2_agentic_voice.voice.protocol import PROTOCOL

# The header a client may carry the offer secret in, instead of the body.
OFFER_SECRET_HEADER = "X-T2V-Offer-Secret"  # noqa: S105 - a header's name, not a secret
MAX_TOKEN_CHARS = 8192  # a join token: a compact JWT of a caller's claims
MAX_OFFER_SECRET_CHARS = 128
MAX_SDP_CHARS = 65_536  # a browser's offer is a few kilobytes
MAX_CANDIDATE_CHARS = 1024  # one ICE candidate line
MAX_CANDIDATES = 64  # in one PATCH
_TOKEN = re.compile(r"[\x21-\x7e]+")  # printable ASCII with no space, as a header carries it


def _token_characters(value: SecretStr) -> SecretStr:
    """`value` when it holds printable ASCII and no space; the error never repeats it."""
    if not _TOKEN.fullmatch(value.get_secret_value()):
        raise ValueError("must hold printable ASCII characters with no space")
    return value


_Token = Annotated[
    SecretStr,
    Field(min_length=1, max_length=MAX_TOKEN_CHARS),
    AfterValidator(_token_characters),
]
_OfferSecret = Annotated[
    SecretStr,
    Field(min_length=1, max_length=MAX_OFFER_SECRET_CHARS),
    AfterValidator(_token_characters),
]


class _Request(BaseModel):
    """A request body: parsed strictly, every size bounded, no value in an error."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class _Response(BaseModel):
    """A response body, built by the router."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class JoinRequest(_Request):
    """`POST /join`: the join token, used once, and the client's protocol version, which the
    router compares with its own, a mismatch answered with a clear notice."""

    token: _Token
    protocol: int = Field(ge=1, le=MAX_INDEX)


class IceServer(_Response):
    """One ICE server, in the shape a browser's `RTCIceServer` takes: its URLs (stun:, turn: or
    turns:) and, for TURN, the call's own user name and password."""

    urls: tuple[str, ...] = Field(min_length=1)
    username: str | None = None
    credential: SecretStr | None = None

    @field_serializer("credential")
    def _revealed(self, value: SecretStr | None) -> str | None:
        """Sent as it is: the browser needs it to reach the TURN server."""
        return None if value is None else value.get_secret_value()


class JoinResponse(_Response):
    """`POST /join`'s answer: the call's ID; its offer secret, random, for this call only, never
    logged, traced or put in an event; the ICE servers; and the server's protocol version."""

    call_id: CallId
    offer_secret: SecretStr
    ice_servers: tuple[IceServer, ...] = ()
    protocol: Literal[1] = PROTOCOL

    @field_serializer("offer_secret")
    def _revealed(self, value: SecretStr) -> str:
        """Sent as it is, to the one client that joined."""
        return value.get_secret_value()


class OfferRequest(_Request):
    """`POST /offer`: the call's SDP offer, once (a second gets 409), with the offer secret here
    or in its header."""

    call_id: CallId
    sdp: str = Field(min_length=1, max_length=MAX_SDP_CHARS)
    type: Literal["offer"]
    offer_secret: _OfferSecret | None = None


class OfferAnswer(_Response):
    """`POST /offer`'s answer: the server's SDP answer, in the shape `setRemoteDescription`
    takes."""

    sdp: str
    type: Literal["answer"] = "answer"


class IceCandidate(_Request):
    """One trickled ICE candidate, as a browser's `RTCIceCandidate` gives it, in snake case: the
    candidate line (empty for the end of candidates), its media's ID and its m-line's index."""

    candidate: str = Field(max_length=MAX_CANDIDATE_CHARS, pattern=r"^[\x20-\x7e]*$")
    sdp_mid: str = Field(pattern=r"^[\x21-\x7e]{1,64}$")
    sdp_mline_index: int = Field(ge=0, le=MAX_INDEX)


class CandidatesRequest(_Request):
    """`PATCH /offer`: the call's trickled candidates, with the offer secret here or in its
    header, until ICE completes (then a quiet 409)."""

    call_id: CallId
    candidates: list[IceCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)
    offer_secret: _OfferSecret | None = None


# Each route of t2v/1, after the router's prefix, with the body it takes and the one it
# answers (None: no body).
BODIES: dict[str, tuple[type[_Request], type[_Response] | None]] = {
    "POST /join": (JoinRequest, JoinResponse),
    "POST /offer": (OfferRequest, OfferAnswer),
    "PATCH /offer": (CandidatesRequest, None),
}
