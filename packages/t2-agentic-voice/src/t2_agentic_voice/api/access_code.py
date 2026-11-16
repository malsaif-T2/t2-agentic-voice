"""The access-code token route, for an app's own demo page: `POST /token` mints a signed join
token for a caller who types the app's access code, carrying the recording choice of the page's
box (D-076). The page joins with it (`t2v/1`'s `/join`), so a call's consent comes from its
signed token alone, and no later message can change it (docs/SECURITY.md, invariant 8). Every
token names the caller the app's `caller` function builds, which neither the request nor
anything said in the call can set (invariant 3). The test console's own tokens (`POST
/voice/dev/token`, under `env` dev) never pass through this route, so they need no code and
leave its counts alone.

The body is JSON alone (415 otherwise, before a byte is read), at most `MAX_BODY_BYTES` (413),
parsed strictly: `{"code": "<access code>", "consent": {"version": ..., "record_audio": ...}}`.
The guard on the shared code, held in this process (a restart begins each count again):
- the code is compared in constant time (`hmac.compare_digest`);
- after each wrong code from an address, that address's next try is refused unread until a
  delay has passed (429 `slowed`, with `Retry-After`): 1 s after its first wrong code in the
  hour, doubling with each, at most 60 s. The address is the connection's peer, or the client a
  trusted proxy forwarded, which uvicorn sets from `server.forwarded_allow_ips` alone;
- the hour's `wrong_per_hour`-th wrong code (20 by default), from any address, closes the route
  until the server restarts (503 `closed`);
- at most `tokens_per_day` tokens a day (10 by default; 429 `daily_limit`, with `Retry-After`).
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

from t2_agentic_voice.api.protocol import is_json
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import get_logger

MAX_BODY_BYTES: Final = 1024
MAX_CODE_CHARS: Final = 256
# The guard's numbers, unless the app gives its own.
WRONG_PER_HOUR: Final = 20
TOKENS_PER_DAY: Final = 10
# How long an address is held back after a wrong code: the first delay, doubling, and the most.
FIRST_DELAY_S: Final = 1.0
LONGEST_DELAY_S: Final = 60.0
HOUR_S: Final = 3600.0
DAY_S: Final = 86_400.0

TokenRefusal = Literal[
    "unsupported_media_type",
    "too_large",
    "invalid_request",
    "wrong_code",
    "slowed",
    "daily_limit",
    "closed",
]
ANSWERS: Final[dict[TokenRefusal, tuple[int, str]]] = {
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


class TokenMinter(Protocol):
    """What mints a join token: `SignedJoinTokens`, with the key `join.current_kid` names."""

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        """A new join token for `caller`, carrying `consent`."""
        ...


@dataclass
class AccessCodeGuard:
    """The route's guard, on `clock` (seconds, monotonic): the wrong codes of the last hour, in
    all and by address, whether the route is closed, and the tokens minted in the last day; the
    route closes at `wrong_per_hour` wrong codes in an hour and mints at most `tokens_per_day`
    tokens a day, each at least 1 (a `ConfigurationError` naming the field otherwise)."""

    clock: Callable[[], float] = time.monotonic
    tokens_per_day: int = TOKENS_PER_DAY
    wrong_per_hour: int = WRONG_PER_HOUR
    closed: bool = False
    _wrong: deque[float] = field(default_factory=deque)
    _by_address: dict[str, deque[float]] = field(default_factory=dict)
    _minted: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        for name in ("tokens_per_day", "wrong_per_hour"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigurationError(
                    f"The access-code guard's {name} must be a whole number of at least 1.",
                    details={"field": name},
                )

    def before_compare(self, address: str) -> tuple[TokenRefusal, float | None] | None:
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
        """Count a wrong code from `address`; the hour's `wrong_per_hour`-th closes the route."""
        now = self.clock()
        self._wrong.append(now)
        self._by_address.setdefault(address, deque()).append(now)
        if len(self._wrong) >= self.wrong_per_hour:
            self.closed = True

    def before_mint(self) -> tuple[TokenRefusal, float | None] | None:
        """Why a token is not minted now, with the seconds until one may be; None when one
        may."""
        now = self.clock()
        self._forget(now)
        if len(self._minted) >= self.tokens_per_day:
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


def access_code_router(
    access_code: SecretStr,
    minter: TokenMinter,
    *,
    caller: Callable[[], Caller],
    guard: AccessCodeGuard | None = None,
) -> APIRouter:
    """The router with `POST /token`, which mints with `minter` for a caller who gives
    `access_code`, each token naming the caller `caller()` builds (the app's, never the
    request's), guarded by `guard` (a new one with the default numbers unless given)."""
    router = APIRouter()
    expected = access_code.get_secret_value().encode()
    held = AccessCodeGuard() if guard is None else guard

    @router.post("/token")
    async def token(request: Request) -> JSONResponse:
        if not is_json(request.headers.get("content-type")):
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
        minted = minter.mint(caller(), consent=asked.consent)
        held.minted()
        log.info("token_minted", record_audio=asked.consent.record_audio)
        return JSONResponse({"token": minted}, headers={"Cache-Control": "no-store"})

    return router


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


def _refused(code: TokenRefusal, retry_after_s: float | None = None) -> JSONResponse:
    """The answer to a refusal: its status, code and message, and when to try again."""
    status, message = ANSWERS[code]
    headers = {"Cache-Control": "no-store"}
    if retry_after_s is not None:
        headers["Retry-After"] = str(max(1, math.ceil(retry_after_s)))
    log.warning("token_refused", reason=code)
    return JSONResponse({"code": code, "message": message}, status_code=status, headers=headers)
