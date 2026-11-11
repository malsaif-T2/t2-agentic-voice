"""The test console (D-083): a page for the engineers who test an agent, beside the dev page,
showing each call on the runtime turn by turn (what was heard, the time of each step, each tool
call with its arguments and result, interruptions, the read-back and the yes rule's decision, the
action's write and its outcome, the models' usage). It is for engineers, never for callers.

- **The feed** (`DevFeed`) is one observer of every event the runtime emits (core/events.py):
  in memory, the records of the last `FEED_CALLS` calls, at most `FEED_RECORDS` in all, each
  numbered in order (`seq`); on disk, every call's events, kept since they are development
  calls (the owner, 2026-11-10): one JSON line per event, appended off the event loop, in
  `<call ID>.jsonl` under `storage.var_dir`'s `dev-console/` (`CONSOLE_FOLDER`), which nothing
  deletes. A start's feed reads the newest `FEED_CALLS` files back, oldest first, before it
  keeps its first event or answers its first page, each line parsed as the event its `type`
  names, a line that is not one skipped. Nothing of it is logged: the events hold call content
  (docs/SECURITY.md, invariant 8); a file that cannot be written or read is logged by the
  failure's kind alone. A restart starts a new feed, named apart (`feed`), so the page knows to
  start over.
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
import secrets
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, ValidationError

from t2_agentic_voice.adapters.dev_identity import is_loopback
from t2_agentic_voice.adapters.join_tokens import SignedJoinTokens
from t2_agentic_voice.api.http_errors import Refusal, answering, read_body
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import EVENTS, CallEnded, Event
from t2_agentic_voice.core.identity import Consent
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.tracing_tts import resource_attributes
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.talker_declaration import DeclaredAction

# The calls whose records the feed keeps, the most records in all, and the longest a feed
# request waits for a new one, in seconds.
FEED_CALLS: Final = 20
FEED_RECORDS: Final = 20_000
WAIT_S: Final = 10.0
# The folder under `storage.var_dir` that holds each call's events, one file a call.
CONSOLE_FOLDER: Final = "dev-console"
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
# Each event's class by the name a saved line gives as its `type`.
_EVENT_TYPES: Final[dict[str, type[Event]]] = {kind.__name__: kind for kind in EVENTS}

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


class DevFeed:
    """The records of the runtime's events, newest last, each call's saved in `folder` when
    given (the module's docstring)."""

    def __init__(
        self, *, folder: Path | None = None, calls: int = FEED_CALLS, records: int = FEED_RECORDS
    ) -> None:
        self.name = secrets.token_hex(4)
        self._folder, self._calls, self._most = folder, calls, records
        self._records: deque[dict[str, JsonValue]] = deque()
        self._order: list[str] = []  # the calls kept, oldest first
        self._seq = 0
        self._new = asyncio.Event()
        self._loading = asyncio.Lock()
        self._loaded = folder is None

    @classmethod
    def of(cls, settings: VoiceSettings) -> DevFeed:
        """The feed of a runtime run with `settings`, its calls saved under `storage.var_dir`."""
        return cls(folder=settings.storage.var_dir / CONSOLE_FOLDER)

    @property
    def last(self) -> int:
        """The number of the newest record, 0 before the first."""
        return self._seq

    async def observe(self, event: Event) -> None:
        """The runtime's observer of every event: kept, then saved in its call's file."""
        await self.ready()
        record = self.add(event)
        if self._folder is not None:
            line = json.dumps(
                {"type": record["type"], "event": record["event"]}, ensure_ascii=False
            )
            await asyncio.to_thread(_save, self._folder, event.call_id, line)

    async def ready(self) -> None:
        """Read the saved calls back, once, before the first event is kept or page answered."""
        if self._loaded or self._folder is None:
            return
        async with self._loading:
            if not self._loaded:
                for event in await asyncio.to_thread(self._saved, self._folder):
                    self.add(event)
                self._loaded = True

    def _saved(self, folder: Path) -> list[Event]:
        """The events of the newest FEED_CALLS calls saved in `folder`, the oldest call's first,
        each call's in order."""
        try:
            files = sorted(folder.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
        except OSError as error:
            _log.warning("dev_console_not_read", failure=type(error).__name__)
            return []
        events: list[Event] = []
        skipped = 0
        for path in files[-self._calls :]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as error:
                _log.warning("dev_console_not_read", failure=type(error).__name__)
                continue
            for line in lines:
                event = _event_of(line)
                skipped += event is None
                if event is not None:
                    events.append(event)
        _log.info("dev_console_read", calls=min(len(files), self._calls), skipped=skipped)
        return events

    def add(self, event: Event) -> dict[str, JsonValue]:
        """Keep `event` as the newest record, returned; the oldest call's records go once more
        calls than FEED_CALLS are kept, and the oldest records once more than FEED_RECORDS."""
        if event.call_id not in self._order:
            self._order.append(event.call_id)
            while len(self._order) > self._calls:
                gone = self._order.pop(0)
                kept = [each for each in self._records if each["call_id"] != gone]
                self._records = deque(kept)
        self._seq += 1
        record: dict[str, JsonValue] = {
            "seq": self._seq,
            "type": type(event).__name__,
            "call_id": event.call_id,
            "ended": isinstance(event, CallEnded),
            "event": event.model_dump(mode="json"),
        }
        self._records.append(record)
        while len(self._records) > self._most:
            self._records.popleft()
        self._new.set()
        self._new = asyncio.Event()
        return record

    def after(self, seq: int) -> list[dict[str, JsonValue]]:
        """The records after `seq`; every record when `seq` is past the newest (an earlier
        feed's number)."""
        start = 0 if seq > self._seq else seq
        return [each for each in self._records if _seq(each) > start]

    async def wait_after(self, seq: int, *, wait_s: float) -> list[dict[str, JsonValue]]:
        """The records after `seq`, at once when there are any, else once one comes or `wait_s`
        has passed (then none)."""
        await self.ready()
        found = self.after(seq)
        if found or wait_s <= 0:
            return found
        new = self._new
        with suppress(TimeoutError):
            async with asyncio.timeout(wait_s):
                await new.wait()
        return self.after(seq)


def _save(folder: Path, call_id: str, line: str) -> None:
    """Append `line` to the call's file in `folder`; `call_id` is a `CallId`, so no path is in
    it. A failure is logged by its kind alone."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{call_id}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
            file.write(line + "\n")
    except OSError as error:
        _log.warning("dev_console_not_saved", call_id=call_id, failure=type(error).__name__)


def _event_of(line: str) -> Event | None:
    """The event a saved line holds, parsed as the class its `type` names; None for a line that
    is not one (blank, not JSON, an unknown type, or fields its class refuses)."""
    try:
        saved = json.loads(line)
        return _EVENT_TYPES[saved["type"]].model_validate(saved["event"])
    except (ValueError, KeyError, TypeError):
        return None


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
    routes: tuple[tuple[str, str, Callable[..., Awaitable[Response]]], ...] = (
        ("GET", "/dev/console", serving(PAGE, "text/html; charset=utf-8", PAGE_HEADERS)),
        ("GET", "/dev/console.js", script),
        ("GET", "/dev/console.css", serving(STYLE, "text/css; charset=utf-8", _FILE_HEADERS)),
        ("GET", "/dev/feed", feed_route),
        ("GET", "/dev/setup", setup_route),
        ("POST", "/dev/token", token_route),
    )
    for method, path, handler in routes:
        route = f"{method} {path}"
        router.add_api_route(
            path, answering(route, handler), methods=[method], include_in_schema=False
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
