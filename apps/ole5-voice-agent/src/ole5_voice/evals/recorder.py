"""`poe record`: the page the owner records the golden set's new takes on, and checks every
variant with (Q9 of plan 002), served by the standard library's `http.server` on 127.0.0.1.

`poe record --out <folder> --session <name> --device <laptop|wired|bluetooth>` logs an address
that holds the session's token; the owner opens it in Chrome. The page asks for the speaker's
consent first, in their words (the session's `session.json`), records each line of the script as
16 kHz mono 16-bit WAV with the browser's echo cancellation, noise suppression and gain control
on, plays the take back, takes a several-clause take's true turn ends from its waveform (and a
stop or pause word's end, or the end of words said over a reply: `ScriptLine.needs_marks`), and
saves it with its sidecar, kept or discarded (`takes.py`). Its review mode plays each kept take,
and each golden-set variant the manifests name below the `--audio <root>=<folder>` roots given,
beside its reference: the owner confirms it, or types what it says. Without `--session` and
`--device` the page only reviews.

The server is the owner's alone (plan 002's decision log): bound to 127.0.0.1, it answers only a
`Host` of `127.0.0.1:<port>` and paths under the session's token, refuses a POST from another
`Origin` or of a body over `MAX_BODY`, and serves only its page and the allow-list of
`recorder_state.py`. It logs no line per request, since a request's path holds the token.
"""

from __future__ import annotations

import argparse
import hmac
import json
import re
import secrets
import sys
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final, cast, get_args

from pydantic import ValidationError
from t2_agentic_voice import configure_logging, get_logger

from ole5_voice import LOGGERS
from ole5_voice.evals import cli
from ole5_voice.evals.items import EVALS, GOLDEN_DIR, MANIFESTS_DIR, SCRIPT_FILE
from ole5_voice.evals.models import Device
from ole5_voice.evals.recorder_load import load_recorder
from ole5_voice.evals.recorder_state import (
    MAX_BODY,
    ConsentUpload,
    Recorder,
    RecorderError,
    RefusedError,
    ReviewUpload,
    TakeUpload,
)

PAGE: Final = Path(__file__).with_name("recorder_page")
_DESCRIPTION = "Serve the page to record the golden set's new takes and check its variants."
_PAGE_FILES: Final = {
    "": ("index.html", "text/html; charset=utf-8"),
    "recorder.js": ("recorder.js", "text/javascript; charset=utf-8"),
}
_JSON: Final = "application/json"
_WAV: Final = "audio/wav"
_HEADERS: Final = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
    "media-src 'self' blob:; connect-src 'self'; img-src data:; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
_SEGMENT: Final = re.compile(r"[0-9]{1,3}")
_LENGTH: Final = re.compile(r"[0-9]{1,12}")
log = get_logger(__name__)


def _dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


class _Handler(BaseHTTPRequestHandler):
    """One request: its body's length, its `Host` and its token checked before anything else,
    and a POST's `Origin` and type before its action."""

    timeout = 30  # seconds; a client that sends nothing more is dropped

    @property
    def _server(self) -> RecorderServer:
        return cast(RecorderServer, self.server)

    def do_GET(self) -> None:
        self._respond(post=False)

    def do_POST(self) -> None:
        self._respond(post=True)

    def _respond(self, *, post: bool) -> None:
        status = HTTPStatus.OK
        try:
            body = self._body() if post else b""  # read first, so no refusal leaves it unread
            route = self._route()
            data, kind = self._post(route, body) if post else self._get(route)
        except RefusedError as refusal:
            status, data, kind = refusal.status, _dumps({"error": str(refusal)}), _JSON
        except ValidationError:
            error = {"error": "the request is not JSON of the fields its action takes"}
            status, data, kind = HTTPStatus.BAD_REQUEST, _dumps(error), _JSON
        self.send_response(status)
        for name, value in {**_HEADERS, "Content-Type": kind}.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> bytes:
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1 or not _LENGTH.fullmatch(lengths[0]):
            raise RefusedError(HTTPStatus.LENGTH_REQUIRED, "a POST gives its body's length")
        if (length := int(lengths[0])) > MAX_BODY:
            raise RefusedError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "the body is too large")
        if len(body := self.rfile.read(length)) != length:
            raise RefusedError(HTTPStatus.BAD_REQUEST, "the body is shorter than its length")
        return body

    def _route(self) -> str:
        """The path below the token, once the `Host` and the token are right."""
        server = self._server
        if self.headers.get_all("Host") != [server.host]:
            raise RefusedError(HTTPStatus.FORBIDDEN, "this recorder answers only its own address")
        prefix = f"/{server.token}/"
        path = self.path.partition("?")[0]  # as sent: never decoded, never a file's path
        if not hmac.compare_digest(path[: len(prefix)].encode("latin-1"), prefix.encode()):
            raise RefusedError(HTTPStatus.FORBIDDEN, "the address needs its token, as logged")
        return path[len(prefix) :]

    def _get(self, route: str) -> tuple[bytes, str]:
        recorder = self._server.recorder
        if route in _PAGE_FILES:
            name, kind = _PAGE_FILES[route]
            return (PAGE / name).read_bytes(), kind
        if route == "api/state":
            return _dumps(recorder.state()), _JSON
        match route.split("/"):
            case ["reply", name]:
                return recorder.reply(name), _WAV
            case ["take", name]:
                return recorder.take(name), _WAV
            case ["variant", name, segment] if _SEGMENT.fullmatch(segment):
                return recorder.variant(name, int(segment)), _WAV
        raise RefusedError(HTTPStatus.NOT_FOUND, "no such page")

    def _post(self, route: str, body: bytes) -> tuple[bytes, str]:
        server = self._server
        if self.headers.get_all("Origin") != [server.origin]:
            raise RefusedError(HTTPStatus.FORBIDDEN, "a POST comes only from this recorder's page")
        if self.headers.get_content_type() != _JSON:
            raise RefusedError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "a POST sends JSON")
        match route:
            case "api/consent":
                done = server.recorder.add_consent(ConsentUpload.model_validate_json(body))
            case "api/take":
                done = server.recorder.add_take(TakeUpload.model_validate_json(body))
            case "api/review":
                done = server.recorder.add_review(ReviewUpload.model_validate_json(body))
            case _:
                raise RefusedError(HTTPStatus.NOT_FOUND, "no such action")
        return _dumps(done), _JSON

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """The status's own phrase only, for what `http.server` refuses itself (an unknown
        method, a bad request line): never the request's text."""
        super().send_error(code)

    def log_message(self, format: str, *args: Any) -> None:
        """No line per request: a request's path holds the session's token."""


class RecorderServer(ThreadingHTTPServer):
    """The recorder's server: on 127.0.0.1 only, with a new token for each run."""

    daemon_threads = True
    allow_reuse_address = False  # on Windows, SO_REUSEADDR would let another socket share it

    def __init__(self, recorder: Recorder, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.recorder = recorder
        self.token = secrets.token_urlsafe(32)
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.address = f"{self.origin}/{self.token}/"


def _port(value: str) -> int:
    if not value.isascii() or not value.isdigit() or int(value) > 65535:
        raise argparse.ArgumentTypeError("a port from 0 (a free one) to 65535")
    return int(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poe record", description=_DESCRIPTION)
    add = parser.add_argument
    add("--out", type=Path, required=True, help="the folder the sessions are written into")
    add("--session", type=cli.name, help="this sitting's name, such as laptop-1")
    add("--device", choices=get_args(Device), help="the microphone this sitting uses")
    add("--script", type=Path, default=EVALS / SCRIPT_FILE, help="the script's lines")
    add("--replies", type=Path, help="the folder of replies.json and the replies it names")
    add(
        "--audio",
        type=cli.audio_root_type,
        action="append",
        default=[],
        metavar="ROOT=FOLDER",
        help="a golden-set audio root, so its variants are checked too",
    )
    add("--golden", type=Path, default=EVALS / GOLDEN_DIR, help="the golden set's items")
    add("--manifests", type=Path, default=EVALS / MANIFESTS_DIR, help="the audio's manifests")
    add("--port", type=_port, default=0, help="its port on 127.0.0.1 (default: a free one)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run poe record`: serve the recorder's page on 127.0.0.1 until Ctrl+C."""
    parser = _parser()
    args = parser.parse_args(argv)
    if (args.session is None) != (args.device is None):
        parser.error("--session and --device go together; give neither to review only")
    try:
        audio = cli.audio_roots(args.audio)
    except ValueError as error:
        parser.error(str(error))
    configure_logging(loggers=LOGGERS)
    try:
        recorder = load_recorder(
            out=args.out,
            script=args.script,
            session=args.session,
            device=args.device,
            replies=args.replies,
            audio=audio,
            golden=args.golden,
            manifests=args.manifests,
        )
        server = RecorderServer(recorder, args.port)
    except (RecorderError, OSError) as error:
        log.error("recorder_not_started", reason=str(error))
        return 2
    for why in recorder.skipped:
        log.warning("recorder_left_out", why=why)
    to_check = sum(1 for entry in recorder.state()["review"] if entry["due"])
    # The one line that holds the token: the owner opens this address in Chrome.
    log.info(
        "recorder_ready",
        address=server.address,
        review_pass=recorder.review_pass,
        to_check=to_check,
    )
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("recorder_closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
