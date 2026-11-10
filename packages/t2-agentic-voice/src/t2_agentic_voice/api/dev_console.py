"""The test console (D-083): a page for the engineers who test an agent, beside the dev page,
showing each call on the runtime turn by turn (what was heard, the time of each step, each tool
call with its arguments and result, interruptions, the read-back and the yes rule's decision, the
action's write and its outcome, the models' usage). It is for engineers, never for callers.

- **The feed** (`DevFeed`) is one observer of every event the runtime emits (core/events.py),
  kept in this process's memory only: the records of the last `FEED_CALLS` calls, at most
  `FEED_RECORDS` in all, each numbered in order (`seq`). Nothing is written to disk and nothing
  is logged: the events hold call content (docs/SECURITY.md, invariant 8). A restart starts a
  new feed, named apart (`feed`), so the page knows to start over.
- **The routes**, after the router's prefix: `GET /dev/console` (the page), `/dev/console.js`
  and `/dev/console.css` (its script and style, from the static folder), `GET /dev/setup`
  (what the agent runs with: its tools, actions, languages, models and the settings that shape
  a turn's timing, never a secret) and `GET /dev/feed?after=N` (the records after `N`, at once
  when there are any, else once one comes or `WAIT_S` passes: long-polling).
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
import secrets
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from t2_agentic_voice.adapters.dev_identity import is_loopback
from t2_agentic_voice.api.http_errors import Refusal, answering
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallEnded, Event
from t2_agentic_voice.core.tracing_tts import resource_attributes
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.talker_declaration import DeclaredAction

# The calls whose records the feed keeps, the most records in all, and the longest a feed
# request waits for a new one, in seconds.
FEED_CALLS: Final = 20
FEED_RECORDS: Final = 20_000
WAIT_S: Final = 10.0
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


class FeedQuery(BaseModel):
    """`GET /dev/feed`'s query: the last record the page has (`after`, 0 for none) and how long
    to wait for a new one (`wait`, in seconds, at most WAIT_S)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    after: int = Field(default=0, ge=0)
    wait: float = Field(default=WAIT_S, ge=0, le=WAIT_S, allow_inf_nan=False)


class DevFeed:
    """The records of the runtime's events, newest last (the module's docstring)."""

    def __init__(self, *, calls: int = FEED_CALLS, records: int = FEED_RECORDS) -> None:
        self.name = secrets.token_hex(4)
        self._calls, self._most = calls, records
        self._records: deque[dict[str, JsonValue]] = deque()
        self._order: list[str] = []  # the calls kept, oldest first
        self._seq = 0
        self._new = asyncio.Event()

    @property
    def last(self) -> int:
        """The number of the newest record, 0 before the first."""
        return self._seq

    async def observe(self, event: Event) -> None:
        """The runtime's observer of every event."""
        self.add(event)

    def add(self, event: Event) -> None:
        """Keep `event` as the newest record; the oldest call's records go once more calls
        than FEED_CALLS are kept, and the oldest records once more than FEED_RECORDS."""
        if event.call_id not in self._order:
            self._order.append(event.call_id)
            while len(self._order) > self._calls:
                gone = self._order.pop(0)
                kept = [each for each in self._records if each["call_id"] != gone]
                self._records = deque(kept)
        self._seq += 1
        self._records.append(
            {
                "seq": self._seq,
                "type": type(event).__name__,
                "call_id": event.call_id,
                "ended": isinstance(event, CallEnded),
                "event": event.model_dump(mode="json"),
            }
        )
        while len(self._records) > self._most:
            self._records.popleft()
        self._new.set()
        self._new = asyncio.Event()

    def after(self, seq: int) -> list[dict[str, JsonValue]]:
        """The records after `seq`; every record when `seq` is past the newest (an earlier
        feed's number)."""
        start = 0 if seq > self._seq else seq
        return [each for each in self._records if _seq(each) > start]

    async def wait_after(self, seq: int, *, wait_s: float) -> list[dict[str, JsonValue]]:
        """The records after `seq`, at once when there are any, else once one comes or `wait_s`
        has passed (then none)."""
        found = self.after(seq)
        if found or wait_s <= 0:
            return found
        new = self._new
        with suppress(TimeoutError):
            async with asyncio.timeout(wait_s):
                await new.wait()
        return self.after(seq)


def _seq(record: dict[str, JsonValue]) -> int:
    value = record["seq"]
    return value if isinstance(value, int) else 0


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

    routes: tuple[tuple[str, Callable[..., Awaitable[Response]]], ...] = (
        ("/dev/console", serving(PAGE, "text/html; charset=utf-8", PAGE_HEADERS)),
        ("/dev/console.js", serving(SCRIPT, "text/javascript; charset=utf-8", _FILE_HEADERS)),
        ("/dev/console.css", serving(STYLE, "text/css; charset=utf-8", _FILE_HEADERS)),
        ("/dev/feed", feed_route),
        ("/dev/setup", setup_route),
    )
    for path, handler in routes:
        route = f"GET {path}"
        router.add_api_route(
            path, answering(route, handler), methods=["GET"], include_in_schema=False
        )


def _json(body: dict[str, JsonValue]) -> Response:
    """`body` as JSON, never cached."""
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return Response(text, media_type="application/json", headers=_FILE_HEADERS)
