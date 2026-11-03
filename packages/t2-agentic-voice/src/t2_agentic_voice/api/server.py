"""Serving a runtime on its own (the design's 4.5, the sidecar): `serve` and `combine_lifespans`.
Built by plan 003's Track F; until then stubs. The items cited are plan 003's appendix, "Changes
to the plan's interfaces"; what Track F builds:

- **The app.** `serve` builds its own FastAPI app with FastAPI's telemetry off,
  `telemetry={"tracing": False, "metrics": False, "logs": False, "auto_configure": False}`,
  which turns it off in FastAPI 0.162.0 (the appendix, step 4, bullet 5): by default FastAPI
  traces, measures and logs every request through OpenTelemetry's global providers, and the
  library instruments no other library (D-023). It includes the runtime's router under
  `prefix`, with CORS for `server.allowed_origins` only: POST and PATCH listed as its methods,
  and as its headers `content-type` and api/protocol.py's `OFFER_SECRET_HEADER`, each of which
  makes a browser ask first (a preflight) before a JSON body or the offer secret's header goes
  to another origin. Track F's test: a preflight for `POST /offer` asking for both headers is
  answered for a listed origin, its `Access-Control-Allow-Origin` that origin; for any other it
  gets Starlette's 400 with no `Access-Control-Allow-Origin`, though it still carries the
  `Access-Control-Allow-Methods`, `-Allow-Headers` and `-Max-Age` CORSMiddleware sends every
  preflight, so a browser refuses the request.
- **uvicorn** runs with one worker, no access log, no server header, no `env_file`, and
  `log_config=None`, so its loggers get no handler of their own (an app names `uvicorn` to
  `configure_logging` for its lines). Proxy headers are off (`proxy_headers=False`) while
  `server.forwarded_allow_ips` is empty, its default, and otherwise trusted from those addresses
  alone (`forwarded_allow_ips`, never `*`): uvicorn's own defaults trust 127.0.0.1 and ::1, so
  any local client could set its address through `X-Forwarded-For`, into the access log too
  (item 19).
- **The event loop.** On Windows uvicorn runs on a selector event loop: on the default proactor
  loop, aioice's UDP sockets stopped receiving after a WinError 10054, and 2 or 3 of 16 call
  closes hung, against 0 of 16 on a selector loop (item 20). Whether uvicorn takes that loop in
  a running server is UNVERIFIED until Track F runs it.
- **Refusals.** `serve` refuses `env` test and a runtime with no identity source, each with a
  FIX line; `t2v dev` alone falls back to `DevIdentity`, binding 127.0.0.1 with proxy headers
  off.

An app that mounts the router in its own app builds that app and runs uvicorn the same way
itself; the guide's serving.md says so.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from t2_agentic_voice.api.runtime import VoiceRuntime

_STUB = "serve and combine_lifespans are built by plan 003's Track F"


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
    raise NotImplementedError(_STUB)


def combine_lifespans[A](
    *lifespans: Callable[[A], AbstractAsyncContextManager[None]],
) -> Callable[[A], AbstractAsyncContextManager[None]]:
    """One lifespan of several, for an app that mounts the router's app as a sub-application,
    whose lifespan FastAPI does not merge (an included router's it does: the design's 4.5): each
    entered in order and left in reverse, and those already entered left when a later one
    fails."""
    raise NotImplementedError(_STUB)
