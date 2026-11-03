"""The Ole5 app's server (plan 003): one FastAPI app that serves Ole5's widget
(apps/ole5-voice-agent/web/), the app's token route (token_route.py) and the library's router
mounted under `VOICE_PREFIX` (the design's 4.5, "The mount"), run by uvicorn with one worker.

`uv run --offline python -m ole5_voice.server --env-file .env` serves it on 127.0.0.1:7861, its
settings from the environment and the file given (settings.py). The app is built as the mount
asks, since there the library's router cannot reach the app's object:
- FastAPI's own telemetry off (`TELEMETRY_OFF`): by default FastAPI traces, measures and logs
  every request through OpenTelemetry's global providers, and the library instruments no other
  library (D-023);
- CORS for `server.allowed_origins` alone, with POST and PATCH, and as headers `content-type`
  and the offer secret's;
- the widget's files with its page's headers (`page_headers`): a Content-Security-Policy with
  no inline script and `frame-ancestors` only the website's origin
  (`OLE5_VOICE_WEBSITE_ORIGIN`), `'none'` while it is unset; `nosniff`; no referrer; the
  microphone for this origin alone.
uvicorn trusts proxy headers only from `server.forwarded_allow_ips`, none by default, so a
client's own `X-Forwarded-For` is ignored; it runs one worker with no access log, no server
header, no log configuration or env file of its own, and on a selector event loop, since on
Windows aioice's sockets stopped receiving on the default proactor loop (plan 003's reading of
the installed packages, item 20 of its changes).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.telemetry import TelemetryConfig
from t2_agentic_voice import (
    ConfigurationError,
    Language,
    VoiceAgent,
    VoiceRuntime,
    VoiceSettings,
    configure_logging,
    get_logger,
)
from t2_agentic_voice.identity import SignedJoinTokens

from ole5_voice import LOGGERS
from ole5_voice.settings import Settings, load
from ole5_voice.token_route import Guard, Minter, token_router

HOST: Final = "127.0.0.1"
PORT: Final = 7861
VOICE_PREFIX: Final = "/voice"
# The widget's folder, beside the app's src/.
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
# The widget's files, by path: each file and its media type.
FILES: Final = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/widget.js": ("widget.js", "text/javascript; charset=utf-8"),
    "/widget.css": ("widget.css", "text/css; charset=utf-8"),
}

# Ole5's agent: Saudi Arabic first, then English, with Ole5's name as each says it, "oo-lee
# faayf" and "Oh-lee five" (the prototype's D26 and D37, Ole5-chatbot/VOICE_LOG.md, lines 35
# and 45). The Arabic texts are written with `\u` escapes, as the library's are, each with its
# sound and meaning in a comment.
AGENT: Final = VoiceAgent(
    name="ole5",
    languages=[
        # hala, ma'ak musaa'id Ole5 as-sawti; takallam wa a'eed 'aleek illi asma'ah: hello, this
        # is Ole5's voice assistant; speak, and I say back to you what I hear.
        Language.saudi_arabic(
            greeting=(
                "\u0647\u0644\u0627\u060c \u0645\u0639\u0643 "
                "\u0645\u0633\u0627\u0639\u062f Ole5 "
                "\u0627\u0644\u0635\u0648\u062a\u064a. \u062a\u0643\u0644\u0651\u0645 "
                "\u0648\u0623\u0639\u064a\u062f \u0639\u0644\u064a\u0643 "
                "\u0627\u0644\u0644\u064a \u0623\u0633\u0645\u0639\u0647."
            )
        ),
        Language.english(
            greeting="Hi, this is the Ole5 voice assistant. Speak, and I will say back what I hear."
        ),
    ],
    # oo-lee faayf
    pronounce={
        "Ole5": {
            "ar": "\u0623\u064f\u0648\u0644\u0650\u064a \u0641\u0627\u064a\u0641",
            "en": "Oh-lee five",
        }
    },
)

log = get_logger(__name__)


def page_headers(website_origin: str | None) -> dict[str, str]:
    """The headers of the widget's files: its page's policy, framed only by `website_origin`
    (none when unset)."""
    ancestors = website_origin or "'none'"
    policy = "; ".join(
        (
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self'",
            "connect-src 'self'",
            "img-src 'self' data:",
            "base-uri 'none'",
            "form-action 'none'",
            f"frame-ancestors {ancestors}",
        )
    )
    return {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "microphone=(self)",
    }


def build_app(
    settings: Settings,
    *,
    router: APIRouter,
    minter: Minter,
    clock: Callable[[], float] = time.monotonic,
    web: Path = WEB,
) -> FastAPI:
    """The app: the widget's files from `web`, the token route minting with `minter` (its
    guard on `clock`), and the library's `router` under VOICE_PREFIX."""
    app = FastAPI(telemetry=TELEMETRY_OFF, openapi_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.voice.server.allowed_origins),
        allow_methods=["POST", "PATCH"],
        allow_headers=["content-type", OFFER_SECRET_HEADER],
    )
    app.include_router(token_router(settings.app.access_code, minter, guard=Guard(clock=clock)))
    app.include_router(router, prefix=VOICE_PREFIX)
    headers = page_headers(settings.app.website_origin)
    for path, (name, media_type) in FILES.items():
        endpoint = _file(web / name, media_type, headers)
        app.add_api_route(path, endpoint, methods=["GET"], include_in_schema=False)
    return app


def make_app(settings: Settings) -> FastAPI:
    """The app as it serves Ole5's calls: the runtime's callers verified by the signed join
    tokens the token route mints, with the key `join.current_kid` names."""
    voice = settings.voice
    tokens = SignedJoinTokens.from_settings(voice.join, prefix=voice.prefix)
    runtime = VoiceRuntime(AGENT, settings=voice, identity=tokens)
    return build_app(settings, router=runtime.router(), minter=tokens)


def server_config(app: FastAPI, voice: VoiceSettings, *, host: str, port: int) -> uvicorn.Config:
    """uvicorn's configuration for `app` on `host` and `port` (module notes)."""
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
    """`python -m ole5_voice.server`: serve the app until the process is stopped."""
    args = _parser().parse_args(argv)
    try:
        settings = load(args.env_file)
        app = make_app(settings)
    except ConfigurationError as error:
        configure_logging(loggers=LOGGERS)
        log.error("server_not_started", reason=error.message)
        return 2
    logs = settings.voice.logging
    configure_logging(logs.level, logs.format, loggers=(*LOGGERS, "uvicorn"), content=logs.content)
    config = server_config(app, settings.voice, host=args.host, port=args.port)
    log.info("server_ready", address=f"http://{args.host}:{args.port}/")
    uvicorn.Server(config).run()
    return 0


def _file(
    path: Path, media_type: str, headers: Mapping[str, str]
) -> Callable[[], Awaitable[FileResponse]]:
    """An endpoint that answers `path` with its headers."""

    async def serve() -> FileResponse:
        return FileResponse(path, media_type=media_type, headers=dict(headers))

    return serve


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ole5_voice.server",
        description="Serve Ole5's widget, its token route and its calls.",
    )
    parser.add_argument("--env-file", type=Path, default=None, help="a .env file to read too")
    parser.add_argument("--host", default=HOST, help=f"the address to bind (default {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"the port (default {PORT})")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
