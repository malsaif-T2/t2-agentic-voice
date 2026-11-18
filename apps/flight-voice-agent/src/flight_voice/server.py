"""The flight agent's server: one FastAPI app that serves its page (apps/flight-voice-agent/web/),
the token route (the library's `access_code_router`, at most `FLIGHT_VOICE_TOKENS_PER_DAY`
tokens a day, 50 by default), the page's own routes (routes.py) and the library's router mounted
under `VOICE_PREFIX`, with its test console under `env` dev, run by uvicorn with one worker.

`uv run --offline python -m flight_voice.server --env-file .env` serves it on 127.0.0.1:7862,
its settings from the environment and the file given (settings.py). Its agent is the one the
setting `FLIGHT_VOICE_AGENT` chooses, today's scripted talker (agent.py) by default or the lean one
beside it (lean/agent.py, D-113, its booking check observing each call's `AgentSpeechEnded`,
`UserTurnEnded` and `CallEnded`, and its calendar's day each `CallStarted`), over the mock
airline, kept in memory and reset to its seed at each start, its modes and today the settings'
(for the lean agent, today as the server starts, the day its calendar is written for, kept; its
flight source the one `FLIGHT_VOICE_FLIGHT_DATA` names, the mock behind the flight data port by
default, flight_data/compose.py's `lean_deps`, closed as the app's lifespan ends, after the
router's); each call's trip is kept in one trip book, dropped as the call ends
(`CallEnded`). Every join token the token route mints names the demo
traveler (traveler.py), whatever the request says. There is no echo: the mock airline needs no
outside service, and the library's runtime needs the Groq key for its chat model and voices
whatever the agent, so with none set it refuses to start, naming the key's setting. The app is
built as the library's mount asks, as Ole5's is:
- FastAPI's own telemetry off (`TELEMETRY_OFF`), since the library instruments no other library
  (D-023);
- CORS for `server.allowed_origins` alone, with POST and PATCH, and as headers `content-type`
  and the offer secret's;
- the page's files with the library's page headers (`page_headers`): a Content-Security-Policy
  with no inline script and `frame-ancestors` only the website's origin
  (`FLIGHT_VOICE_WEBSITE_ORIGIN`), `'none'` while it is unset; `nosniff`; no referrer; the
  microphone for this origin alone.
uvicorn trusts proxy headers only from `server.forwarded_allow_ips`, none by default; it runs one
worker with no access log, no server header, no log configuration or env file of its own, on a
selector event loop (aioice's sockets stop receiving on Windows's default proactor loop).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, Final, Protocol

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.telemetry import TelemetryConfig
from t2_agentic_voice import (
    ConfigurationError,
    VoiceRuntime,
    VoiceSettings,
    configure_logging,
    get_logger,
)
from t2_agentic_voice.events import CallEnded, CallStarted, Event
from t2_agentic_voice.identity import SignedJoinTokens
from t2_agentic_voice.server import (
    AccessCodeGuard,
    TokenMinter,
    access_code_router,
    page_headers,
)

from flight_voice import LOGGERS
from flight_voice.agent import declare
from flight_voice.airline.bookings import BookingStore
from flight_voice.airline.system import Airline
from flight_voice.flight_data.compose import lean_deps
from flight_voice.lean.agent import OBSERVED, calendar_watch
from flight_voice.lean.agent import declare as declare_lean
from flight_voice.routes import api_router
from flight_voice.settings import AppSettings, Settings, load
from flight_voice.traveler import demo_caller
from flight_voice.trip import TripBook

HOST: Final = "127.0.0.1"
PORT: Final = 7862
VOICE_PREFIX: Final = "/voice"
# The page's folder, beside the app's src/.
WEB: Final = Path(__file__).resolve().parents[2] / "web"
TELEMETRY_OFF: Final[TelemetryConfig] = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "auto_configure": False,
}
# The header a client may carry a call's offer secret in (t2v/1), allowed through CORS.
OFFER_SECRET_HEADER: Final = "X-T2V-Offer-Secret"  # noqa: S105 - a header's name, not a secret
# A selector loop on every system (uvicorn's `module:attribute` form of a loop factory).
SELECTOR_LOOP: Final = "asyncio:SelectorEventLoop"
_JS: Final = "text/javascript; charset=utf-8"
# The page's files, by path: each file and its media type.
FILES: Final = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", _JS),
    "/cards.js": ("cards.js", _JS),
    "/orb.js": ("orb.js", _JS),
    "/bookings.js": ("bookings.js", _JS),
    "/texts.js": ("texts.js", _JS),
    "/mark.svg": ("mark.svg", "image/svg+xml"),
}
# The page's files are asked again each load (an ETag answers 304 when unchanged).
REVALIDATE: Final = {"Cache-Control": "no-cache"}

# An app's lifespan, as FastAPI keeps it on its router: the app in, a context out.
Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]

log = get_logger(__name__)


class Closable(Protocol):
    """What the app closes as its lifespan ends: the lean agent's flight source."""

    async def aclose(self) -> None: ...


def airline_of(app: AppSettings, today: Callable[[], date] | None = None) -> Airline:
    """The mock airline as the settings set it: its today (`today` when given), its modes and
    its code, its bookings the seed."""
    today = app.today_source() if today is None else today
    bookings = BookingStore(today=today, mode=app.booking_mode, lookup=app.booking_lookup)
    return Airline(
        today=today,
        bookings=bookings,
        search_mode=app.search_mode,
        profile_mode=app.profile_mode,
        slow_s=app.slow_s,
        code=app.airline_code,
    )


def build_app(
    settings: Settings,
    *,
    router: APIRouter,
    minter: TokenMinter,
    airline: Airline,
    clock: Callable[[], float] = time.monotonic,
    web: Path = WEB,
    closing: Sequence[Closable] = (),
) -> FastAPI:
    """The app: the page's files from `web`, the token route minting with `minter` (its guard
    on `clock`) for the demo traveler, the page's routes over `airline`, and the library's
    `router` under VOICE_PREFIX; each of `closing` closed as the app's lifespan ends, after the
    router's."""
    app = FastAPI(telemetry=TELEMETRY_OFF, openapi_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.voice.server.allowed_origins),
        allow_methods=["POST", "PATCH"],
        allow_headers=["content-type", OFFER_SECRET_HEADER],
    )
    guard = AccessCodeGuard(clock=clock, tokens_per_day=settings.app.tokens_per_day)
    app.include_router(
        access_code_router(settings.app.access_code, minter, caller=demo_caller, guard=guard)
    )
    real = settings.app.agent == "lean" and settings.app.flight_data != "mock"
    app.include_router(api_router(airline, settings.app.names(), "real" if real else "mock"))
    app.include_router(router, prefix=VOICE_PREFIX)
    if closing:  # the router's lifespan, merged into the app's as included, runs inside
        app.router.lifespan_context = _around(app.router.lifespan_context, closing)
    headers = page_headers(settings.app.website_origin)
    for path, (name, media_type) in FILES.items():
        endpoint = _file(web / name, media_type, headers)
        app.add_api_route(path, endpoint, methods=["GET"], include_in_schema=False)
    return app


def make_app(settings: Settings) -> FastAPI:
    """The app as it serves the flight agent's calls: the runtime's callers verified by the
    signed join tokens the token route mints, with the key `join.current_kid` names; its agent
    the one `app.agent` chooses over the mock airline the settings set, each call's trip
    dropped as it ends, and for the lean agent its booking check observing each call's events
    (lean/agent.py)."""
    voice = settings.voice
    tokens = SignedJoinTokens.from_settings(voice.join, prefix=voice.prefix)
    names = settings.app.names()
    observers: list[tuple[type[Event], Callable[[Event], Awaitable[None]]]] = []
    closing: list[Closable] = []
    if settings.app.agent == "lean":
        day = settings.app.today_source()()  # the calendar's, kept as the airline's today
        airline = airline_of(settings.app, today=lambda: day)
        deps = lean_deps(settings.app, airline, names, today=lambda: day)
        agent = declare_lean(deps, names)
        ended: Callable[[CallEnded], Awaitable[None]] = deps.trips.call_ended
        observers += [(kind, deps.check.observed) for kind in OBSERVED]
        observers.append((CallStarted, calendar_watch(day)))
        closing.append(deps.data)
    else:
        airline = airline_of(settings.app)
        trips = TripBook()
        agent = declare(airline, trips, names)
        ended = trips.call_ended
    runtime = VoiceRuntime(agent, settings=voice, identity=tokens)
    runtime.on(CallEnded)(ended)
    for kind, observer in observers:
        runtime.on(kind)(observer)
    log.info(
        "airline_ready",
        today=str(settings.app.today),
        search=settings.app.search_mode,
        agent=agent.name,
    )
    router = runtime.router()
    return build_app(settings, router=router, minter=tokens, airline=airline, closing=closing)


def server_config(app: FastAPI, voice: VoiceSettings, *, host: str, port: int) -> uvicorn.Config:
    """uvicorn's configuration for `app` on `host` and `port` (the module's docstring)."""
    trusted = list(voice.server.forwarded_allow_ips)
    return uvicorn.Config(
        app,
        host=host,
        port=port,
        workers=1,
        proxy_headers=bool(trusted),
        forwarded_allow_ips=trusted,
        access_log=False,
        server_header=False,
        log_config=None,
        env_file=None,
        loop=SELECTOR_LOOP,
        lifespan="on",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m flight_voice.server`: serve the app until the process is stopped."""
    args = _parser().parse_args(argv)
    try:
        settings = load(args.env_file)
    except ConfigurationError as error:
        configure_logging(loggers=LOGGERS)
        log.error("server_not_started", reason=error.message)
        return 2
    logs = settings.voice.logging
    configure_logging(logs.level, logs.format, loggers=(*LOGGERS, "uvicorn"), content=logs.content)
    try:
        app = make_app(settings)
    except ConfigurationError as error:
        log.error("server_not_started", reason=error.message)
        return 2
    config = server_config(app, settings.voice, host=args.host, port=args.port)
    log.info("server_ready", address=f"http://{args.host}:{args.port}/")
    uvicorn.Server(config).run()
    return 0


def _around(inner: Lifespan, closing: Sequence[Closable]) -> Lifespan:
    """A lifespan that runs `inner` (the app's, the routers' merged into it) and closes each of
    `closing`, in order, however `inner` ended."""

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[Any]:
        try:
            async with inner(app) as state:
                yield state
        finally:
            for resource in closing:
                await resource.aclose()

    return lifespan


def _file(
    path: Path, media_type: str, headers: Mapping[str, str]
) -> Callable[[], Awaitable[FileResponse]]:
    """An endpoint that answers `path` with its headers, revalidated on every load, so a page
    updated on the server never runs beside a cached older module of itself."""

    async def serve() -> FileResponse:
        return FileResponse(path, media_type=media_type, headers=dict(headers) | REVALIDATE)

    return serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flight_voice.server",
        description="Serve the flight agent's page, its token route and its calls.",
    )
    parser.add_argument("--env-file", type=Path, default=None, help="a .env file to read too")
    parser.add_argument("--host", default=HOST, help=f"the address to bind (default {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"the port (default {PORT})")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
