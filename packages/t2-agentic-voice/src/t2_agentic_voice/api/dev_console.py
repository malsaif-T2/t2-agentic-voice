"""The test console (D-083): a page for the engineers who test an agent, beside the dev page,
showing each call on the runtime turn by turn (what was heard, the time of each step, each tool
call with its arguments and result, interruptions, the read-back and the yes rule's decision, the
action's write and its outcome, the models' usage). It is for engineers, never for callers.

- **The feed** (api/dev_feed.py's `DevFeed`) is one observer of every event the runtime emits,
  kept in memory and on disk, and read back at a start.
- **The routes**, after the router's prefix: `GET /dev/console` (the page), `/dev/console.js`
  and `/dev/console.css` (its script and style, from the static folder), `GET /dev/setup`
  (what the agent runs with: its tools, actions, languages, models and the settings that shape
  a turn's timing, never a secret), `GET /dev/feed?after=N` (the records after `N`, at once
  when there are any, else once one comes or `WAIT_S` passes: long-polling) and
  `POST /dev/token`, the token the page's Start joins with when its field is left empty.
- **The token** (the owner, 2026-11-11): a signed join token, as the app's own token route
  mints, from `SignedJoinTokens.from_settings(settings.join)`, for the caller the app declares
  (`server.dev_caller`), never one a request names (invariant 3). Its body is the page's
  keep-audio box alone (`TokenAsk`, at most `MAX_TOKEN_BYTES`), its consent the server's
  `privacy.consent_version`. No access code and no count of the app's own apply. With no dev
  caller, or no join key that signs (`join.current_kid`), it answers the plain 404, logged as
  `dev_token_refused` with why, and the page joins with `dev`. The token is never logged:
  `dev_token_minted` holds the consent's `record_audio` alone.
- **On this machine, under dev, only.** The routes are mounted with the dev page alone (`env`
  dev and `server.dev_page`, or `t2v dev`), and each answers the server's plain 404 under any
  other `env`, to a client that is not loopback, and to a request whose `Host` is not a
  loopback name (`localhost`, `127.0.0.1`, `[::1]`), so a page elsewhere cannot reach it through
  a name it points at this machine. The page's headers allow scripts and styles from the server
  alone and no framing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, ValidationError

from t2_agentic_voice.adapters.dev_identity import is_loopback
from t2_agentic_voice.adapters.join_tokens import SignedJoinTokens
from t2_agentic_voice.api.dev_feed import DevFeed
from t2_agentic_voice.api.http_errors import Refusal, add_routes, read_body
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Consent
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing_tts import resource_attributes
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.talker_declaration import DeclaredAction

# The longest a feed request waits for a new record, in seconds.
WAIT_S: Final = 10.0
# The most bytes `POST /dev/token` reads: its body is `{"record_audio": false}`.
MAX_TOKEN_BYTES: Final = 256
PAGE: Final = "dev-console.html"
SCRIPT: Final = "dev-console.js"
STYLE: Final = "dev-console.css"
# The settings groups the setup shows: none holds a secret (a test).
SETUP_GROUPS: Final = ("stt", "llm", "tts", "turns", "interruptions", "limits")
_POLICY: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src data:; media-src 'self' blob:; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
PAGE_HEADERS: Final = {
    "Content-Security-Policy": _POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self)",
    "Cache-Control": "no-store",
}
_FILE_HEADERS: Final = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
_LOOPBACK_NAMES: Final = frozenset({"localhost"})

Read = Callable[[str], Awaitable[bytes]]

_log = get_logger(__name__)


class FeedQuery(BaseModel):
    """`GET /dev/feed`'s query: the last record the page has (`after`, 0 for none) and how long
    to wait for a new one (`wait`, in seconds, at most WAIT_S)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    after: int = Field(default=0, ge=0)
    wait: float = Field(default=WAIT_S, ge=0, le=WAIT_S, allow_inf_nan=False)


class TokenAsk(BaseModel):
    """`POST /dev/token`'s body: whether the call's audio may be kept (the page's box, false
    unless given), and nothing else: the caller is the app's (`server.dev_caller`)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    record_audio: StrictBool = False


def setup_of(agent: VoiceAgent, settings: VoiceSettings) -> dict[str, JsonValue]:
    """What the agent runs with, as the console shows it: its name, version, languages, mode,
    tools and actions; the library's and Pipecat's versions and the settings' digest; and the
    settings groups that shape a turn (SETUP_GROUPS), none of which holds a secret."""
    tools = [tool.name for tool in agent.tools if not isinstance(tool, DeclaredAction)]
    actions = [tool.name for tool in agent.tools if isinstance(tool, DeclaredAction)]
    library = resource_attributes(settings, agent=agent.name, models=(), consent_version=None)
    mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    groups: dict[str, JsonValue] = {
        group: getattr(settings, group).model_dump(mode="json") for group in SETUP_GROUPS
    }
    return {
        "agent": agent.name,
        "version": agent.version,
        "env": settings.env,
        "mode": mode,
        "languages": [language.tag for language in agent.languages],
        "tools": list(tools),
        "actions": list(actions),
        "ask_on_uncertain_overlaps": agent.ask_on_uncertain_overlaps,
        "ask_on_unlisted_answers": agent.ask_on_unlisted_answers,
        "library": {key: value for key, value in library.items() if isinstance(value, str)},
        "settings": groups,
    }


def loopback_host(host: str | None) -> bool:
    """Whether a request's `Host` names this machine's loopback: `localhost`, or a loopback
    address (`127.0.0.1`, `[::1]`), with or without a port."""
    if not host:
        return False
    name = host[1:].partition("]")[0] if host.startswith("[") else host.rpartition(":")[0]
    name = name or host
    return name.lower() in _LOOPBACK_NAMES or is_loopback(name)


def mount_console(
    router: APIRouter,
    *,
    agent: VoiceAgent,
    settings: VoiceSettings,
    feed: DevFeed,
    running: Callable[[], object | None],
    read: Read,
) -> None:
    """Add the console's routes to `router` (the module's docstring): its files read with
    `read`, its feed `feed`, each route 503 `not_started` while `running` gives None."""
    setup = setup_of(agent, settings)

    def admitted(request: Request) -> None:
        client = None if request.client is None else request.client.host
        if settings.env != "dev" or not is_loopback(client):
            raise HTTPException(status_code=404)
        if not loopback_host(request.headers.get("host")):
            raise HTTPException(status_code=404)
        if running() is None:
            raise Refusal(503, "not_started")

    def serving(
        name: str, media: str, headers: dict[str, str]
    ) -> Callable[..., Awaitable[Response]]:
        async def serve(request: Request, reference: str) -> Response:
            admitted(request)
            return Response(await read(name), media_type=media, headers=headers)

        return serve

    async def feed_route(request: Request, reference: str) -> Response:
        admitted(request)
        try:
            query = FeedQuery.model_validate(dict(request.query_params))
        except ValidationError:
            raise Refusal(400, "invalid_request") from None
        records: list[JsonValue] = list(await feed.wait_after(query.after, wait_s=query.wait))
        body: dict[str, JsonValue] = {"feed": feed.name, "last": feed.last, "records": records}
        return _json(body)

    async def setup_route(request: Request, reference: str) -> Response:
        admitted(request)
        return _json(setup)

    async def token_route(request: Request, reference: str) -> Response:
        admitted(request)
        caller = settings.server.dev_caller
        if caller is None:
            _log.info("dev_token_refused", reason="no_dev_caller")
            raise HTTPException(status_code=404)
        body = await read_body(request, MAX_TOKEN_BYTES)
        try:
            asked = TokenAsk.model_validate_json(body)
        except ValidationError:
            raise Refusal(400, "invalid_request") from None
        tokens = await asyncio.to_thread(_signer, settings)
        if tokens is None:
            _log.info("dev_token_refused", reason="no_join_key")
            raise HTTPException(status_code=404)
        consent = Consent(version=settings.privacy.consent_version, record_audio=asked.record_audio)
        token = tokens.mint(caller, consent=consent)
        _log.info("dev_token_minted", record_audio=asked.record_audio)
        return _json({"token": token})

    script = serving(SCRIPT, "text/javascript; charset=utf-8", _FILE_HEADERS)
    add_routes(
        router,
        ("GET", "/dev/console", serving(PAGE, "text/html; charset=utf-8", PAGE_HEADERS)),
        ("GET", "/dev/console.js", script),
        ("GET", "/dev/console.css", serving(STYLE, "text/css; charset=utf-8", _FILE_HEADERS)),
        ("GET", "/dev/feed", feed_route),
        ("GET", "/dev/setup", setup_route),
        ("POST", "/dev/token", token_route),
    )


def _signer(settings: VoiceSettings) -> SignedJoinTokens | None:
    """The signed join tokens the join settings describe, when they hold a key and name the one
    that signs (`join.current_kid`); None otherwise. The keys may be read from a file."""
    if settings.join.current_kid is None:
        return None
    try:
        return SignedJoinTokens.from_settings(settings.join, prefix=settings.prefix)
    except ConfigurationError:
        return None


def _json(body: dict[str, JsonValue]) -> Response:
    """`body` as JSON, never cached."""
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return Response(text, media_type="application/json", headers=_FILE_HEADERS)
