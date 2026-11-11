"""The one error shape of `t2v/1`'s routes, and how a route reads its body (api/runtime.py,
"Bodies" and "Errors"; D-029; GP-19).

A route raises `Refusal` with a status and a code its `BODIES` entry lists; `answering` turns it
into api/protocol.py's `ErrorBody`, with a message fixed per code that never holds a value the
request sent, and a reference made for the request and logged with the refusal's event. A
crash is answered the same way, 500 `internal_error`, and logged by its type alone. The quiet
409s, which a connected client ignores, are logged at DEBUG.

`read_body` reads a route's body as the router does: `application/json` alone (415 before a
byte is read), never past the route's cap (413, from a `Content-Length` over it or as the body
streams past it), so no body is buffered whole.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import HTTPException, Request, Response

from t2_agentic_voice.api.protocol import ErrorBody, ErrorCode, Route, is_json
from t2_agentic_voice.core.logging import get_logger

# The message of each code, safe to show the caller: it never holds a value the request sent.
MESSAGES: Final[dict[ErrorCode, str]] = {
    "invalid_request": "The request's body is not one t2v/1 takes.",
    "too_large": "The request's body is larger than this route takes.",
    "unsupported_media_type": "The request's body must be sent as application/json.",
    "protocol_mismatch": "The client speaks another version of the protocol than this server's.",
    "join_rejected": "The join token was refused.",
    "forbidden": "The offer secret is missing, wrong or not this call's.",
    "already_offered": "This call's offer was taken already.",
    "not_offered": "This call's offer has not been answered.",
    "ice_completed": "This call is connected: it takes no more candidates.",
    "call_ended": "This call has ended.",
    "not_started": "The voice runtime has not started.",
    "internal_error": "The server failed to answer this request.",
}
# The 409s a connected client ignores, logged at DEBUG.
QUIET: Final = frozenset({"not_offered", "ice_completed", "call_ended"})

Handler = Callable[[Request], Awaitable[Response]]

log = get_logger(__name__)


class Refusal(Exception):  # noqa: N818 - a route's answer, not a failure
    """A route's refusal: its status and code, and the body to send when it is not the code's
    fixed one (a refused body's types, a protocol mismatch's notice)."""

    def __init__(self, status: int, code: ErrorCode, *, body: ErrorBody | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code: ErrorCode = code
        self.body = body


def reference() -> str:
    """A request's reference: random, never taken from the request."""
    return secrets.token_urlsafe(12)


def error_response(status: int, body: ErrorBody) -> Response:
    """`body` sent with `status`."""
    return Response(body.model_dump_json(), status_code=status, media_type="application/json")


def error_body(code: ErrorCode, *, reference: str) -> ErrorBody:
    """The body of `code` with its fixed message."""
    return ErrorBody(code=code, message=MESSAGES[code], reference=reference)


def answering(route: str, handler: Callable[[Request, str], Awaitable[Response]]) -> Handler:
    """`handler` as a route: it gets the request and its reference, and every refusal it raises,
    and every crash, is answered in the one error shape and logged with the reference."""

    async def answer(request: Request) -> Response:
        ref = reference()
        try:
            return await handler(request, ref)
        except HTTPException:
            raise  # the server's own answer (a plain 404), as for a path it does not have
        except Refusal as refusal:
            body = refusal.body or error_body(refusal.code, reference=ref)
            logged = log.debug if refusal.code in QUIET else log.info
            logged("request_refused", route=route, code=refusal.code, reference=ref)
            return error_response(refusal.status, body)
        except Exception as error:  # a crash: answered in the one shape, logged by its type
            log.error("request_failed", route=route, error=type(error).__name__, reference=ref)
            return error_response(500, error_body("internal_error", reference=ref))

    return answer


async def read_body(request: Request, route: Route | int) -> bytes:
    """The request's body, sent as JSON and within `route`'s cap (or the bytes given, for a
    route that is not `t2v/1`'s, the test console's); a `Refusal` otherwise (415 before a byte
    is read; 413 for a `Content-Length` over the cap, or at the cap as the body streams past
    it)."""
    cap = route if isinstance(route, int) else route.max_bytes
    if not is_json(request.headers.get("content-type")):
        raise Refusal(415, "unsupported_media_type")
    if _declared(request.headers.get("content-length")) > cap:
        raise Refusal(413, "too_large")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > cap:
            raise Refusal(413, "too_large")
    return bytes(body)


def _declared(length: str | None) -> int:
    """The length a `Content-Length` header declares; 0 when it declares none it can read, the
    body then counted as it streams."""
    try:
        return int(length or "0")
    except ValueError:
        return 0
