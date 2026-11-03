"""The HTTP bodies of `t2v/1` (the design's 5.5), after the router's prefix: `POST /join` takes a
join token, the client's protocol version and the language the caller picked, and answers the
call's ID, its offer secret, the ICE servers and the server's version; `POST /offer` takes the
call's SDP offer and answers its SDP answer; `PATCH /offer` takes trickled ICE candidates, an
empty one marking their end (plan 003's appendix, item 14). The data channel's messages are
voice/protocol.py's.

A request body comes from the browser, which is not trusted: it is parsed strictly, with
exactly its fields, each of its JSON type, and every size bounded (the bounds are the agent's,
each well over what a browser sends). A route takes a body sent as JSON alone (`is_json`, else
415 before a byte is read), reads it itself, refusing it past its route's cap in bytes before
parsing it, and parses it with the model's `model_validate_json`, answering a refusal with
`refusal`; `/join` reads the body's protocol version first, alone (`version_mismatch`). A
model's ValidationError keeps the input out of its text and repr (though they name a key the
client added), but its `errors()` and `json()` carry it, and FastAPI answers a model declared
as a body parameter with its own 422, which sends `errors()` back, input and all. The offer
secret is the call's alone: it rides in the `OFFER_SECRET_HEADER` header or the body's
`offer_secret`, never in a URL, which logs and traces keep. The call ID is no credential (the
design's 5.5), and a client never sends Pipecat's `pc_id`, which `voice` keeps behind the call
ID (the appendix, item 10).

Every refusal and failure of a `t2v/1` route, a crash included, answers `ErrorBody`, the one
error shape (GP-19), with a status and a code `BODIES` lists for its route.

A secret (the offer secret, the join token, a TURN password) is a `SecretStr` here, so no repr,
log line or python-mode dump of a body shows it; a response reveals its own only as it is
serialized to JSON (`model_dump(mode="json")`, `model_dump_json()`), as it is sent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    ValidationError,
    field_serializer,
    model_validator,
)

from t2_agentic_voice.core.events import MAX_INDEX, CallId
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.voice.protocol import PROTOCOL

# The header a client may carry the offer secret in, instead of the body.
OFFER_SECRET_HEADER = "X-T2V-Offer-Secret"  # noqa: S105 - a header's name, not a secret
MAX_TOKEN_CHARS = 8192  # a join token: a compact JWT of a caller's claims
MAX_OFFER_SECRET_CHARS = 128
MAX_SDP_CHARS = 65_536  # a browser's offer is a few kilobytes
MAX_CANDIDATE_CHARS = 1024  # one ICE candidate line
MAX_CANDIDATES = 64  # in one PATCH
_TOKEN = re.compile(r"[\x21-\x7e]+")  # printable ASCII with no space, as a header carries it
# An SDP as a browser writes it: printable ASCII, tabs and line breaks.
_SDP = r"^[\x09\x0a\x0d\x20-\x7e]+$"

# Each route's cap on its body in bytes, enforced as the body streams in, before it is parsed
# (over it: 413, `too_large`): twice the longest values the body holds, and 4 KiB for its names
# and punctuation. Twice, since every field the caps count takes printable ASCII alone (the SDP
# tabs and line breaks too), which a browser's JSON.stringify or Python's json.dumps writes in
# two bytes a character at most (a quote, a backslash, a tab or a line break, each escaped).
_SLACK = 4096
MAX_JOIN_BYTES = 2 * MAX_TOKEN_CHARS + _SLACK
MAX_OFFER_BYTES = 2 * (MAX_SDP_CHARS + MAX_OFFER_SECRET_CHARS) + _SLACK
# A candidate's line, and 128 for its media's ID, its index and its names.
MAX_CANDIDATES_BYTES = (
    2 * (MAX_CANDIDATES * (MAX_CANDIDATE_CHARS + 128) + MAX_OFFER_SECRET_CHARS) + _SLACK
)

# What an error body's code says went wrong: the body is not one t2v/1 takes
# (`invalid_request`), is over its route's cap (`too_large`) or is not sent as JSON
# (`unsupported_media_type`); the client speaks another protocol version (`protocol_mismatch`);
# the join token is refused (`join_rejected`); the offer secret is missing, wrong or not this
# call's (`forbidden`); the call's offer was answered already (`already_offered`); a PATCH with
# the call's own secret came before voice answered its offer (`not_offered`: not yet, or
# refused), after ICE completed, or after the call ended (`ice_completed`, `call_ended`): the
# quiet 409s, logged at DEBUG, which the client ignores once connected; the runtime has not
# started (`not_started`); anything else, a crash included (`internal_error`).
ErrorCode = Literal[
    "invalid_request",
    "too_large",
    "unsupported_media_type",
    "protocol_mismatch",
    "join_rejected",
    "forbidden",
    "already_offered",
    "not_offered",
    "ice_completed",
    "call_ended",
    "not_started",
    "internal_error",
]
# A request's reference: random, made by the router for each refusal (for example
# `secrets.token_urlsafe(12)`), never taken from the request.
REFERENCE_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
# The one media type a route's body is sent as.
JSON_TYPE = "application/json"
# A join of another protocol version: what the client is told, and the notice its page shows
# the caller, in Arabic and in English, since no language the caller picked is read from a body
# of another version (the agent's words, for the owner to change).
MISMATCH_MESSAGE = "The client speaks another version of the protocol than this server's, t2v/1."
MISMATCH_NOTICE = (
    "هذه الصفحة قديمة: أعد تحميلها لتتصل من جديد. "
    "This page is out of date: reload it to call again."
)


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
    """A request body: parsed strictly, every size bounded. Its refusal's text and repr hold no
    value it was given (they name a key the client added), but its `errors()` and `json()` hold
    both: a route answers it with `refusal` alone."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class _Response(BaseModel):
    """A response body, built by the router."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class JoinRequest(_Request):
    """`POST /join`: the join token, used once; the client's protocol version, which the router
    reads first, from the body as any JSON with nothing else of it (`version_mismatch`), before
    this strict parse and before it verifies the token, so a client of another version gets
    its clear notice (`protocol_mismatch`) whatever else its body holds, and spends no token;
    and the language the caller picked in the client, if any, one of the library's tags, from
    which with the token's locale the router fixes the call's language
    (`VoiceAgent.call_language`)."""

    token: _Token
    protocol: int = Field(ge=1, le=MAX_INDEX)
    language: LanguageTag | None = None


class IceServer(_Response):
    """One ICE server, in the shape a browser's `RTCIceServer` takes: its URLs (stun:, turn: or
    turns:) and, for TURN, the call's own user name and password."""

    urls: tuple[str, ...] = Field(min_length=1)
    username: str | None = None
    credential: SecretStr | None = None

    @field_serializer("credential", when_used="json")
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

    @field_serializer("offer_secret", when_used="json")
    def _revealed(self, value: SecretStr) -> str:
        """Sent as it is, to the one client that joined."""
        return value.get_secret_value()


class OfferRequest(_Request):
    """`POST /offer`: the call's SDP offer, printable ASCII with tabs and line breaks, as a
    browser writes it, once (a second gets 409), with the offer secret here or in its
    header."""

    call_id: CallId
    sdp: str = Field(min_length=1, max_length=MAX_SDP_CHARS, pattern=_SDP)
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
    header, until ICE completes (then a quiet 409). A client sends them only once `POST /offer`
    has answered: before that, or after a refused offer, a PATCH gets the quiet 409
    `not_offered`."""

    call_id: CallId
    candidates: list[IceCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)
    offer_secret: _OfferSecret | None = None


class ErrorBody(_Response):
    """Every route's answer to a refusal or a failure, a crash included (GP-19): its `code`; a
    `message` safe to show the caller, which never holds a value the request sent; with
    `protocol_mismatch` alone, the `notice` a page shows the caller in place of a dead call (the
    design's 5.4); and the request's `reference`, which the router logs with the refusal's
    event, so a caller's report leads to its log lines."""

    code: ErrorCode
    message: str = Field(min_length=1)
    notice: str | None = Field(default=None, min_length=1)
    reference: str = Field(pattern=REFERENCE_PATTERN)

    @model_validator(mode="after")
    def _notice_with_a_mismatch(self) -> ErrorBody:
        if (self.notice is not None) != (self.code == "protocol_mismatch"):
            raise ValueError("a notice comes with protocol_mismatch, and only with it")
        return self


class _Version(BaseModel):
    """A `/join` body as the version check reads it: any JSON object, for its `protocol`
    alone."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    protocol: JsonValue = None


def is_json(content_type: str | None) -> bool:
    """Whether a request's `Content-Type` says its body is JSON, the one kind every `t2v/1`
    route takes: `application/json` in any case, with any parameter (`charset=utf-8`). A route
    answers a request with none, or with any other type, 415 (`unsupported_media_type`) before
    it reads the body: a page on any origin may send a form or text/plain to another with no
    CORS preflight, and a JSON body never goes without one."""
    if content_type is None:
        return False
    essence, _, _ = content_type.partition(";")
    return essence.strip(" \t").lower() == JSON_TYPE


def version_mismatch(body: bytes, *, reference: str) -> ErrorBody | None:
    """The answer to a `/join` body of another protocol version (400, `protocol_mismatch`,
    with its notice), read before the strict parse so that a client of any version gets it,
    whatever else its body holds: the body, within its cap, is read as any JSON for its
    top-level `protocol` alone, and any value but the JSON integer `PROTOCOL` names another
    version (a string, a float, a boolean or null among them). None when the body names this
    version or none, or is not a JSON object: the strict parse answers it then."""
    try:
        found = _Version.model_validate_json(body)
    except ValidationError:
        return None
    version = found.protocol
    if "protocol" not in found.model_fields_set or (type(version) is int and version == PROTOCOL):
        return None
    return ErrorBody(
        code="protocol_mismatch",
        message=MISMATCH_MESSAGE,
        notice=MISMATCH_NOTICE,
        reference=reference,
    )


def refusal(error: ValidationError, *, reference: str) -> ErrorBody:
    """The answer to a body its model refused (400, `invalid_request`): its message names only
    the kinds of problem pydantic found (its error types), never a value, a key or a type the
    client sent, all of which the error's `errors()` and `json()` carry."""
    found = error.errors(include_url=False, include_context=False, include_input=False)
    problems = ", ".join(sorted({each["type"] for each in found}))
    return ErrorBody(
        code="invalid_request",
        message=f"The request's body is not one t2v/1 takes ({problems}).",
        reference=reference,
    )


@dataclass(frozen=True, kw_only=True)
class Route:
    """One route of `t2v/1`: the body it takes, and its cap in bytes; on success, its status and
    the body it answers (None: none); and the codes it answers in an `ErrorBody`, by status."""

    request: type[_Request]
    max_bytes: int
    status: int
    response: type[_Response] | None
    errors: Mapping[int, tuple[ErrorCode, ...]]


# What any route may answer: a body over its cap or not sent as JSON, a crash, or a runtime
# not started.
_ANY_ROUTE: dict[int, tuple[ErrorCode, ...]] = {
    413: ("too_large",),
    415: ("unsupported_media_type",),
    500: ("internal_error",),
    503: ("not_started",),
}


def _answers(own: Mapping[int, tuple[ErrorCode, ...]]) -> dict[int, tuple[ErrorCode, ...]]:
    """A route's own error codes by status, and those any route may answer."""
    return {**own, **_ANY_ROUTE}


# Each route of t2v/1, after the router's prefix.
BODIES: dict[str, Route] = {
    "POST /join": Route(
        request=JoinRequest,
        max_bytes=MAX_JOIN_BYTES,
        status=200,
        response=JoinResponse,
        errors=_answers({400: ("invalid_request", "protocol_mismatch"), 403: ("join_rejected",)}),
    ),
    "POST /offer": Route(
        request=OfferRequest,
        max_bytes=MAX_OFFER_BYTES,
        status=200,
        response=OfferAnswer,
        errors=_answers(
            {400: ("invalid_request",), 403: ("forbidden",), 409: ("already_offered",)}
        ),
    ),
    "PATCH /offer": Route(
        request=CandidatesRequest,
        max_bytes=MAX_CANDIDATES_BYTES,
        status=204,
        response=None,
        errors=_answers(
            {
                400: ("invalid_request",),
                403: ("forbidden",),
                409: ("not_offered", "ice_completed", "call_ended"),
            }
        ),
    ),
}
