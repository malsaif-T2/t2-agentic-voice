"""The routes a runtime serves (api/runtime.py; the design's 4.5 and 5.5; D-029), after the prefix
an app includes them under: `t2v/1`'s `POST /join`, `POST` and `PATCH /offer`, and `GET /health`
(what the design's 10.5 lists that is built: the environment and the live calls), `GET /ready`
and `GET /client/1/t2v-client.js`; and `GET /dev`, no `t2v/1` route, only with `env` dev and
the dev page on, to loopback clients, `env` checked before the client's address is read, any
other getting the server's plain 404. With the dev page come the test console's routes, under
`/dev/` (api/dev_console.py).

- **`/join`** reads the client's protocol version first, and answers a body of another version
  400 `protocol_mismatch`, with its notice, before the strict parse and before the token is
  verified; verifies the token once; refuses a `SignedConsent` whose version is not
  `privacy.consent_version` when that is set (a plain `Consent`, as `DevIdentity` gives, is not
  compared: D-029); fixes the call's language (`agent.call_language(request.language,
  locale=caller.locale)`, kept to the call's end); and mints the call's ID and offer secret
  (api/offers.py). It answers `server.ice_servers` as they are set, with no user name or
  credential: it mints no TURN credentials (the owner's ruling of 2026-11-03; TD-048).
- **`POST /offer`** hands voice the call's caller, consent and language with the offer
  (`Calls.answer`). A call takes one offer: a second, or one after voice refused the first, gets
  409 `already_offered`. The offer secret, in the `X-T2V-Offer-Secret` header or the body, never
  in a URL, stops working when ICE completes or the call ends, and the call's own secret then
  gets a 409, never a 403: a PATCH a quiet 409, logged at DEBUG with no value, `ice_completed`
  once the call's `phase` is `connected`, and `call_ended` once it is `ended`, or None once
  voice has forgotten it. A PATCH with the call's own secret before voice answered its offer
  (not yet, or refused) gets the quiet 409 `not_offered`; `forbidden` (403) is for a secret
  that is missing, wrong or not this call's, or a call whose record was dropped. A client's
  `pc_id` never reaches Pipecat (plan 003's appendix, item 10).
- **Every route**, `/health`, `/ready`, the client script and `/dev` included, answers 503
  `not_started` while the runtime's lifespan has not run, or has ended (the decision log,
  2026-11-03), in the one error shape; every refusal and crash of a route is answered in it too
  (api/http_errors.py). No route declares a body parameter: each reads and parses its own body.
  The browser's files, `t2v-client.js` and `dev.html`, are read from `STATIC` when first asked
  for, off the event loop, and kept.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from t2_agentic_voice.adapters.dev_identity import is_loopback
from t2_agentic_voice.api.dev_console import mount_console
from t2_agentic_voice.api.dev_feed import DevFeed
from t2_agentic_voice.api.http_errors import Refusal, add_routes, read_body
from t2_agentic_voice.api.offers import CallRecord, CallRecords
from t2_agentic_voice.api.protocol import (
    BODIES,
    OFFER_SECRET_HEADER,
    CandidatesRequest,
    IceServer,
    JoinRequest,
    JoinResponse,
    OfferAnswer,
    OfferRequest,
    version_mismatch,
)
from t2_agentic_voice.api.protocol import refusal as refused_body
from t2_agentic_voice.core.config import Environment, VoiceSettings
from t2_agentic_voice.core.errors import InvalidRequestError, JoinRejected, NotFoundError
from t2_agentic_voice.core.identity import Consent, SignedConsent
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext, UsedTokens
from t2_agentic_voice.voice.calls import Calls, Candidate
from t2_agentic_voice.voice.protocol import PROTOCOL
from t2_agentic_voice.voice.session.io import Clock

# The browser's files the router serves, shipped in the library's wheel.
STATIC: Final = Path(__file__).parent / "static"
CLIENT_SCRIPT: Final = "t2v-client.js"
DEV_PAGE: Final = "dev.html"
_SCRIPT_HEADERS: Final = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
# The dev page's headers: a policy that loads the client script alone, talks only to
# the page's own origin, takes only a data: image (the page's empty icon) and is never framed
# (the browser criterion), since dev.html holds no script, style or handler of its own; no
# referrer, the microphone for the page itself.
_DEV_POLICY: Final = (
    "default-src 'none'; script-src 'self'; connect-src 'self'; img-src data:; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)
_PAGE_HEADERS: Final = {
    "Content-Security-Policy": _DEV_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self)",
    "Cache-Control": "no-store",
}

log = get_logger(__name__)


@dataclass(frozen=True)
class Running:
    """What a started runtime's routes use: voice's calls and the used-token store."""

    calls: Calls
    used_tokens: UsedTokens


@dataclass(frozen=True, kw_only=True)
class Served:
    """What the router serves: the agent with its settings and identity source, the records of
    its calls, the runtime's clock, what it runs (None until started), where the browser's files
    are, whether `/dev` is mounted, and the test console's feed (mounted with `/dev`)."""

    agent: VoiceAgent
    settings: VoiceSettings
    identity: IdentityVerifier
    records: CallRecords
    clock: Clock
    running: Callable[[], Running | None]
    static: Path = STATIC
    dev_page: bool = False
    feed: DevFeed | None = None
    _files: dict[str, bytes] = field(default_factory=dict)


class Health(BaseModel):
    """`GET /health`: what the design's 10.5 lists that is built, no path: the environment and
    the calls voice holds live. The cap and the cool-off come with admission control."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    env: Environment
    calls: int


class Ready(BaseModel):
    """`GET /ready`: the runtime has started and takes calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: Literal[True] = True


def build_router(
    served: Served, *, lifespan: Callable[[object], AbstractAsyncContextManager[None]]
) -> APIRouter:
    """The runtime's routes over `served`, carrying `lifespan`."""
    routes = _Routes(served)
    router = APIRouter(lifespan=lifespan)
    add_routes(
        router,
        ("POST", "/join", routes.join),
        ("POST", "/offer", routes.offer),
        ("PATCH", "/offer", routes.candidates),
        ("GET", "/health", routes.health),
        ("GET", "/ready", routes.ready),
        ("GET", f"/client/{PROTOCOL}/{CLIENT_SCRIPT}", routes.client),
    )
    if served.dev_page:
        add_routes(router, ("GET", "/dev", routes.dev))
        if served.feed is not None:
            mount_console(
                router,
                agent=served.agent,
                settings=served.settings,
                feed=served.feed,
                running=served.running,
                read=routes._file,
            )
    return router


class _Routes:
    """The route handlers over one `Served`."""

    def __init__(self, served: Served) -> None:
        self._served = served
        self._settings = served.settings

    def _running(self) -> Running:
        running = self._served.running()
        if running is None:
            raise Refusal(503, "not_started")
        return running

    async def join(self, request: Request, reference: str) -> Response:
        running = self._running()
        body = await read_body(request, BODIES["POST /join"])
        mismatch = version_mismatch(body, reference=reference)
        if mismatch is not None:
            raise Refusal(400, "protocol_mismatch", body=mismatch)
        parsed = _parsed(JoinRequest, body, reference)
        context = JoinContext(
            env=self._settings.env, client_host=_host(request), used_tokens=running.used_tokens
        )
        try:
            caller, consent = await self._served.identity.verify(
                parsed.token.get_secret_value(), join=context
            )
        except JoinRejected:
            raise Refusal(403, "join_rejected") from None
        if self._wrong_version(consent):
            raise Refusal(403, "join_rejected")
        language = self._served.agent.call_language(parsed.language, locale=caller.locale)
        record = self._served.records.join(
            caller=caller, consent=consent, language=language, now=self._served.clock.now()
        )
        log.info("call_joined", call_id=record.call_id, language=language.tag)
        servers = tuple(IceServer(urls=(url,)) for url in self._settings.server.ice_servers)
        answer = JoinResponse(
            call_id=record.call_id, offer_secret=record.secret, ice_servers=servers
        )
        return _json(answer)

    def _wrong_version(self, consent: Consent) -> bool:
        """Whether a signed consent names another version than `privacy.consent_version`, when
        that is set; a plain consent, which never lets audio be kept, is not compared (D-029)."""
        wanted = self._settings.privacy.consent_version
        return (
            wanted is not None
            and isinstance(consent, SignedConsent)
            and (consent.version != wanted)
        )

    async def offer(self, request: Request, reference: str) -> Response:
        running = self._running()
        body = await read_body(request, BODIES["POST /offer"])
        parsed = _parsed(OfferRequest, body, reference)
        record = self._record(request, parsed.call_id, parsed.offer_secret)
        joined = record.offering()
        if joined is None:
            raise Refusal(409, "already_offered")
        try:
            sdp = await running.calls.answer(
                record.call_id,
                parsed.sdp,
                caller=joined.caller,
                consent=joined.consent,
                language=joined.language,
            )
        except InvalidRequestError:
            record.offer = "refused"
            raise Refusal(400, "invalid_request") from None
        except BaseException:
            record.offer = "refused"
            await _ended(running.calls, record.call_id)
            raise
        record.offer = "answered"
        log.info("call_offered", call_id=record.call_id)
        return _json(OfferAnswer(sdp=sdp))

    async def candidates(self, request: Request, reference: str) -> Response:
        running = self._running()
        body = await read_body(request, BODIES["PATCH /offer"])
        parsed = _parsed(CandidatesRequest, body, reference)
        record = self._record(request, parsed.call_id, parsed.offer_secret)
        if record.offer != "answered":
            raise Refusal(409, "not_offered")
        phase = running.calls.phase(record.call_id)
        if phase == "connected":
            raise Refusal(409, "ice_completed")
        if phase != "connecting":
            raise Refusal(409, "call_ended")
        candidates = [
            Candidate(candidate=c.candidate, sdp_mid=c.sdp_mid, sdp_mline_index=c.sdp_mline_index)
            for c in parsed.candidates
        ]
        try:
            await running.calls.add_candidates(record.call_id, candidates)
        except NotFoundError:
            raise Refusal(409, "call_ended") from None
        except InvalidRequestError:
            raise Refusal(400, "invalid_request") from None
        log.debug("candidates_added", call_id=record.call_id, count=len(candidates))
        return Response(status_code=204)

    def _record(self, request: Request, call_id: str, in_body: SecretStr | None) -> CallRecord:
        """The call's record, found with the offer secret its header or its body carries (both,
        when both carry one and they agree); 403 `forbidden` otherwise."""
        header = request.headers.get(OFFER_SECRET_HEADER)
        body = None if in_body is None else in_body.get_secret_value()
        secret = header if body is None else body if header in (None, body) else None
        record = self._served.records.find(call_id, secret)
        if record is None:
            raise Refusal(403, "forbidden")
        return record

    async def health(self, request: Request, reference: str) -> Response:
        running = self._running()
        live = self._served.records.live(running.calls.phase)
        return _json(Health(env=self._settings.env, calls=live))

    async def ready(self, request: Request, reference: str) -> Response:
        self._running()
        return _json(Ready())

    async def client(self, request: Request, reference: str) -> Response:
        self._running()
        script = await self._file(CLIENT_SCRIPT)
        media = "text/javascript; charset=utf-8"
        return Response(script, media_type=media, headers=_SCRIPT_HEADERS)

    async def dev(self, request: Request, reference: str) -> Response:
        """The dev page: `env` dev is checked before the client's address is read, and any other
        `env`, or a client that is not loopback (adapters/dev_identity.py's `is_loopback`, as the
        dev caller and the test console read it), gets the server's plain 404."""
        if self._settings.env != "dev" or not is_loopback(_host(request)):
            raise HTTPException(status_code=404)
        self._running()
        page = await self._file(DEV_PAGE)
        return Response(page, media_type="text/html; charset=utf-8", headers=_PAGE_HEADERS)

    async def _file(self, name: str) -> bytes:
        """The browser's file `name`, read from the static folder once, off the event loop; the
        server's plain 404 when it is missing."""
        files = self._served._files
        if name not in files:
            try:
                files[name] = await asyncio.to_thread((self._served.static / name).read_bytes)
            except FileNotFoundError:
                raise HTTPException(status_code=404) from None
        return files[name]


def _parsed[M: BaseModel](model: type[M], body: bytes, reference: str) -> M:
    """`body` parsed strictly as `model`; a refusal naming pydantic's error types otherwise."""
    try:
        return model.model_validate_json(body)
    except ValidationError as error:
        answer = refused_body(error, reference=reference)
    raise Refusal(400, "invalid_request", body=answer)


async def _ended(calls: Calls, call_id: str) -> None:
    """End a call whose offer failed, in case voice holds part of it; a failure is logged."""
    try:
        await calls.end(call_id)
    except Exception as error:
        log.warning("call_end_failed", call_id=call_id, error=type(error).__name__)


def _json(model: BaseModel) -> Response:
    """`model` as a JSON response, its secrets revealed as it is sent."""
    return Response(model.model_dump_json(), media_type="application/json")


def _host(request: Request) -> str | None:
    """The client's address as the server saw it (a trusted proxy's forwarded one included)."""
    return None if request.client is None else request.client.host
