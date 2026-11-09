"""The Ole5 app's token route (plan 003, Q4): `POST /token` mints a signed join token for a
caller who types the owner's access code, carrying the recording choice of the widget's box
(D-076). The widget joins with it (`t2v/1`'s `/join`), so a call's consent comes from
its signed token alone, and no later message can change it (docs/SECURITY.md, invariant 8).

The body is JSON alone (415 otherwise, before a byte is read), at most `MAX_BODY_BYTES` (413),
parsed strictly: `{"code": "<access code>", "consent": {"version": ..., "record_audio": ...}}`.
Q4's guard on the shared key, held in this process (the owner runs the backend only during call
sessions, so a restart begins each count again):
- the code is compared in constant time (`hmac.compare_digest`);
- after each wrong code from an address, that address's next try is refused unread until a
  delay has passed (429 `slowed`, with `Retry-After`): 1 s after its first wrong code in the
  hour, doubling with each, at most 60 s. The address is the connection's peer, or the client a
  trusted proxy forwarded, which uvicorn sets from `server.forwarded_allow_ips` alone
  (server.py);
- the 20th wrong code within an hour, from any address, closes the route until the server
  restarts (503 `closed`);
- at most 10 tokens a day (429 `daily_limit`, with `Retry-After`).
Every refusal is `{"code": ..., "message": ...}`, a message safe to show that holds no value the
request sent, and is logged with its code alone.
"""

from __future__ import annotations

import hmac
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal, Protocol

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from t2_agentic_voice import Caller, Consent, get_logger

# The caller every token names: the owner, the only one who holds the code.
SUBJECT: Final = "owner"
MAX_BODY_BYTES: Final = 1024
MAX_CODE_CHARS: Final = 256
# Q4's numbers.
WRONG_PER_HOUR: Final = 20
TOKENS_PER_DAY: Final = 10
# How long an address is held back after a wrong code: the first delay, doubling, and the most.
FIRST_DELAY_S: Final = 1.0
LONGEST_DELAY_S: Final = 60.0
HOUR_S: Final = 3600.0
DAY_S: Final = 86_400.0
JSON_TYPE: Final = "application/json"

Refusal = Literal[
    "unsupported_media_type",
    "too_large",
    "invalid_request",
    "wrong_code",
    "slowed",
    "daily_limit",
    "closed",
]
ANSWERS: Final[dict[Refusal, tuple[int, str]]] = {
    "unsupported_media_type": (415, "The request's body is sent as application/json."),
    "too_large": (413, "The request's body is too large."),
    "invalid_request": (400, "The request's body is not a code and a consent."),
    "wrong_code": (403, "The access code is not right."),
    "slowed": (429, "Too many tries from this address: try again later."),
    "daily_limit": (429, "Today's tokens have all been given: try again tomorrow."),
    "closed": (503, "Too many wrong codes: the route is closed until the server restarts."),
}

log = get_logger(__name__)


class TokenRequest(BaseModel):
    """`POST /token`'s body: the access code, and the recording choice made on the page."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    code: Annotated[SecretStr, Field(min_length=1, max_length=MAX_CODE_CHARS)]
    consent: Consent


class Minter(Protocol):
    """What mints a join token: `SignedJoinTokens`, with the key `join.current_kid` names."""

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        """A new join token for `caller`, carrying `consent`."""
        ...


@dataclass
class Guard:
    """Q4's guard, on `clock` (seconds, monotonic): the wrong codes of the last hour, in all and
    by address, whether the route is closed, and the tokens minted in the last day."""

    clock: Callable[[], float] = time.monotonic
    closed: bool = False
    _wrong: deque[float] = field(default_factory=deque)
    _by_address: dict[str, deque[float]] = field(default_factory=dict)
    _minted: deque[float] = field(default_factory=deque)

    def before_compare(self, address: str) -> tuple[Refusal, float | None] | None:
        """Why a try from `address` is refused before its code is read, with the seconds until
        it may try again; None when it is not."""
        if self.closed:
            return "closed", None
        now = self.clock()
        self._forget(now)
        wrong = self._by_address.get(address)
        if wrong:
            ready = wrong[-1] + min(FIRST_DELAY_S * 2 ** (len(wrong) - 1), LONGEST_DELAY_S)
            if now < ready:
                return "slowed", ready - now
        return None

    def wrong_code(self, address: str) -> None:
        """Count a wrong code from `address`; the hour's WRONG_PER_HOUR-th closes the route."""
        now = self.clock()
        self._wrong.append(now)
        self._by_address.setdefault(address, deque()).append(now)
        if len(self._wrong) >= WRONG_PER_HOUR:
            self.closed = True

    def before_mint(self) -> tuple[Refusal, float | None] | None:
        """Why a token is not minted now, with the seconds until one may be; None when one
        may."""
        now = self.clock()
        self._forget(now)
        if len(self._minted) >= TOKENS_PER_DAY:
            return "daily_limit", self._minted[0] + DAY_S - now
        return None

    def minted(self) -> None:
        """Count a token minted."""
        self._minted.append(self.clock())

    def _forget(self, now: float) -> None:
        """Drop what is older than its window, so the guard holds at most an hour's wrong codes
        and a day's tokens."""
        for times, window in ((self._wrong, HOUR_S), (self._minted, DAY_S)):
            while times and times[0] <= now - window:
                times.popleft()
        for address, times in list(self._by_address.items()):
            while times and times[0] <= now - HOUR_S:
                times.popleft()
            if not times:
                del self._by_address[address]


def token_router(
    access_code: SecretStr, minter: Minter, *, guard: Guard | None = None
) -> APIRouter:
    """The router with `POST /token`, which mints with `minter` for a caller who gives
    `access_code`, guarded by `guard` (a new one unless given)."""
    router = APIRouter()
    expected = access_code.get_secret_value().encode()
    held = Guard() if guard is None else guard

    @router.post("/token")
    async def token(request: Request) -> JSONResponse:
        if not _is_json(request.headers.get("content-type")):
            return _refused("unsupported_media_type")
        body = await _read(request)
        if body is None:
            return _refused("too_large")
        address = request.client.host if request.client else "unknown"
        early = held.before_compare(address)
        if early is not None:
            return _refused(*early)
        try:
            asked = TokenRequest.model_validate_json(body)
        except ValidationError:
            return _refused("invalid_request")  # its errors hold the code: not chained
        if not hmac.compare_digest(asked.code.get_secret_value().encode(), expected):
            held.wrong_code(address)
            return _refused("wrong_code")
        late = held.before_mint()
        if late is not None:
            return _refused(*late)
        minted = minter.mint(Caller(subject=SUBJECT), consent=asked.consent)
        held.minted()
        log.info("token_minted", record_audio=asked.consent.record_audio)
        return JSONResponse({"token": minted}, headers={"Cache-Control": "no-store"})

    return router


def _is_json(content_type: str | None) -> bool:
    """Whether a `Content-Type` says JSON, with any parameter (`charset=utf-8`)."""
    essence = (content_type or "").partition(";")[0]
    return essence.strip(" \t").lower() == JSON_TYPE


async def _read(request: Request) -> bytes | None:
    """The request's body, or None once it passes MAX_BODY_BYTES, by its length or as it
    streams in."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            return None
    return bytes(body)


def _refused(code: Refusal, retry_after_s: float | None = None) -> JSONResponse:
    """The answer to a refusal: its status, code and message, and when to try again."""
    status, message = ANSWERS[code]
    headers = {"Cache-Control": "no-store"}
    if retry_after_s is not None:
        headers["Retry-After"] = str(max(1, math.ceil(retry_after_s)))
    log.warning("token_refused", reason=code)
    return JSONResponse({"code": code, "message": message}, status_code=status, headers=headers)
