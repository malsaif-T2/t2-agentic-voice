"""Serving a runtime on its own (the design's 4.5, the sidecar): `serve` and `combine_lifespans`.
The items cited are plan 003's appendix, "Changes to the plan's interfaces".

- **The app.** `serve` builds its own FastAPI app (`build_app`) with FastAPI's telemetry off,
  `telemetry={"tracing": False, "metrics": False, "logs": False, "auto_configure": False}`,
  which turns it off in FastAPI 0.162.0 (the appendix, step 4, bullet 5): by default FastAPI
  traces, measures and logs every request through OpenTelemetry's global providers, and the
  library instruments no other library (D-023). It has no docs, OpenAPI or ReDoc page. It
  includes the runtime's router under `prefix`, with CORS for `server.allowed_origins` only:
  POST and PATCH listed as its methods, and as its headers `content-type` and api/protocol.py's
  `OFFER_SECRET_HEADER`, each of which makes a browser ask first (a preflight) before a JSON
  body or the offer secret's header goes to another origin. A preflight for a listed origin is
  answered with that origin; for any other it gets Starlette's 400 with no
  `Access-Control-Allow-Origin`, so a browser refuses the request.
- **uvicorn** (`uvicorn_config`) runs with one worker, no access log, no server header, no
  `env_file`, and `log_config=None`, so its loggers get no handler of their own (an app names
  `uvicorn` to `configure_logging` for its lines). Proxy headers are off
  (`proxy_headers=False`) while `server.forwarded_allow_ips` is empty, its default, and under
  `t2v dev`, and otherwise trusted from those addresses alone (`forwarded_allow_ips`, never
  `*`): uvicorn's own defaults trust 127.0.0.1 and ::1, so any local client could set its
  address through `X-Forwarded-For`, into the access log too (item 19). Every value uvicorn
  would read from a variable (`FORWARDED_ALLOW_IPS`, `WEB_CONCURRENCY`) is passed.
- **The event loop.** uvicorn runs on a selector event loop (`asyncio.SelectorEventLoop`, on
  every platform, given to `asyncio.run`): on Windows' default proactor loop, aioice's UDP
  sockets stopped receiving after a WinError 10054, and 2 or 3 of 16 call closes hung, against
  0 of 16 on a selector loop (item 20). tests/t2_agentic_voice/api/test_serving.py runs a server
  in a child process and finds its loop is one.
- **Refusals.** `serve` refuses `env` test and a runtime with no identity source, each with a
  FIX line, before uvicorn starts; `t2v dev` alone falls back to `DevIdentity`, binding
  127.0.0.1 with proxy headers off and the dev page on (`serve_dev`).

An app that mounts the router in its own app builds that app and runs uvicorn the same way
itself; the guide's serving.md says so.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Final

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.telemetry import TelemetryConfig

from t2_agentic_voice.api.protocol import OFFER_SECRET_HEADER
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings

# FastAPI's own telemetry, off (D-023).
TELEMETRY_OFF: Final[TelemetryConfig] = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "auto_configure": False,
}
# What a cross-origin page may send, so a browser's preflight passes for a listed origin.
CORS_METHODS: Final = ("POST", "PATCH")
CORS_HEADERS: Final = ("content-type", OFFER_SECRET_HEADER)
# The address `t2v dev` binds: this machine only.
LOOPBACK: Final = "127.0.0.1"


def serve(
    factory: Callable[[], VoiceRuntime],
    *,
    host: str = "127.0.0.1",
    port: int = 7860,
    prefix: str = "/voice",
) -> None:
    """Serve the runtime `factory` makes (called once) until the process is stopped: on `host`
    (this machine's loopback unless given) and `port` (the design's 4.2 serves on 7860), the
    router under `prefix` (the design's `/voice`). The sidecar: `t2v serve APP` runs it."""
    runtime = factory()
    app = build_app(runtime, prefix=prefix)
    run(uvicorn_config(app, host=host, port=port, settings=runtime._settings, proxy=True))


def serve_dev(
    factory: Callable[[], VoiceRuntime], *, port: int = 7860, prefix: str = "/voice"
) -> None:
    """`t2v dev`: the runtime `factory` makes, under `env` dev only, on 127.0.0.1 with proxy
    headers off, its dev page on, and `DevIdentity` when it has no identity source."""
    runtime = factory()
    app = build_app(runtime, prefix=prefix, dev=True)
    run(uvicorn_config(app, host=LOOPBACK, port=port, settings=runtime._settings, proxy=False))


def build_app(runtime: VoiceRuntime, *, prefix: str, dev: bool = False) -> FastAPI:
    """`serve`'s app: FastAPI's telemetry off and no docs pages, the runtime's router under
    `prefix` (its lifespan merged), and CORS for `server.allowed_origins` alone."""
    router = runtime._router(dev=dev)
    app = FastAPI(telemetry=TELEMETRY_OFF, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router, prefix=prefix)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime._settings.server.allowed_origins),
        allow_methods=list(CORS_METHODS),
        allow_headers=list(CORS_HEADERS),
    )
    runtime._served = True
    return app


def uvicorn_config(
    app: FastAPI, *, host: str, port: int, settings: VoiceSettings, proxy: bool
) -> uvicorn.Config:
    """uvicorn's settings for `app`: one worker, no access log, server header, env file or
    logging config of its own, and proxy headers trusted only from `server.forwarded_allow_ips`
    when `proxy` and that is set."""
    trusted = list(settings.server.forwarded_allow_ips) if proxy else []
    return uvicorn.Config(
        app,
        host=host,
        port=port,
        workers=1,
        access_log=False,
        server_header=False,
        env_file=None,
        log_config=None,
        lifespan="on",
        proxy_headers=bool(trusted),
        forwarded_allow_ips=trusted,
    )


def run(config: uvicorn.Config) -> None:
    """Run uvicorn with `config` on a selector event loop until the process is stopped."""
    server = uvicorn.Server(config)
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)


def combine_lifespans[A](
    *lifespans: Callable[[A], AbstractAsyncContextManager[None]],
) -> Callable[[A], AbstractAsyncContextManager[None]]:
    """One lifespan of several, for an app that mounts the router's app as a sub-application,
    whose lifespan FastAPI does not merge (an included router's it does: the design's 4.5): each
    entered in order and left in reverse, and those already entered left when a later one
    fails."""

    @asynccontextmanager
    async def combined(app: A) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for lifespan in lifespans:
                await stack.enter_async_context(lifespan(app))
            yield

    return combined
