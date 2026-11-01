"""What the tracing tests share (test_tracing.py, test_tracing_export.py): made-up values, a turn
with its speech-to-text span, a private provider on the in-memory exporter, and an OTLP/HTTP
collector on 127.0.0.1."""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.core.tracing import Tracing

MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
TOKEN = f"Bearer {MADE_UP_KEY}"
PHONE = "0512345678"
RESOURCE = {"service.name": "t2-agentic-voice", "openinference.project.name": "golden-set"}
NOBODY = "http://127.0.0.1:9"  # the discard port: nothing answers
SENT_HEADERS = {"host", "user-agent", "content-type", "content-length", "accept-encoding"}
Received = list[tuple[str, dict[str, str], bytes]]  # each request's path, headers and body


def settings_with(tmp_path: Path, **tracing: object) -> Settings:
    values = {"env": "test", "var_dir": tmp_path, "groq": {"api_key": MADE_UP_KEY}}
    return Settings.model_validate(values | {"tracing": {"project": "golden-set"} | tracing})


def one_turn(tracing: Tracing, text: str = "hello there") -> None:
    with (
        tracing.turn(session_id="run-1") as turn,
        tracing.speech_to_text(turn, model="m-1", language="ar", audio_seconds=1.5) as stt,
    ):
        stt.record(text=text, language="ar", billed_seconds=10.0)


def turns(tracing: Tracing, count: int) -> None:
    for _ in range(count):
        with tracing.turn(session_id="more"):
            pass


def private(**kwargs: Any) -> tuple[Tracing, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return Tracing(exporter=exporter, **({"project": "golden-set"} | kwargs)), exporter


def finished(tracing: Tracing, exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    tracing.shutdown()
    return {span.name: span for span in exporter.get_finished_spans()}


def exported_text(spans: Sequence[ReadableSpan]) -> str:
    """Everything a span exports, as text: names, attributes, events, links, status, resource."""
    parts: list[object] = []
    for span in spans:
        parts += [span.name, dict(span.attributes or {}), span.status.description]
        parts += [(e.name, dict(e.attributes or {})) for e in span.events]
        parts += [dict(link.attributes or {}) for link in span.links]
        parts += [dict(span.resource.attributes), span.instrumentation_scope]
    return repr(parts)


@contextmanager
def collector(status: int, hold: threading.Event | None = None) -> Iterator[tuple[str, Received]]:
    """An OTLP/HTTP collector on 127.0.0.1 answering `status`; with `hold`, it answers nothing
    until `hold` is set, and then drops the request, whose client has given up."""
    received: Received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
            if hold is not None:
                hold.wait(10)
                return
            self.send_response(status)
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1/traces", received
    finally:
        if hold is not None:
            hold.set()
        server.shutdown()
        server.server_close()
