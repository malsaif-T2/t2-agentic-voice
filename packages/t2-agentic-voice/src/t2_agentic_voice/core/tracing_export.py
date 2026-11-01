"""The private provider `core.tracing` builds when a team passes no provider of its own: its
bounded export queue, the provider itself, and the OTLP exporter with its own session.

Nothing here blocks or raises into the thread that ends a span, and every value the SDK and its
exporter would read from an `OTEL_*` variable is passed (plan 002's decision log);
`OTEL_SDK_DISABLED` and `OTEL_PYTHON_CONTEXT` are read whatever is passed (TD-005). Moved out
of `core/tracing.py`, which had reached ARCH-SIZE's cap, in plan 002's review of the merged
tracks.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from importlib.metadata import version
from typing import Any

import requests
from openinference.semconv.resource import ResourceAttributes
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, SpanProcessor
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from opentelemetry.util.types import AnyValue

from t2_agentic_voice.core.logging import get_logger

_log = get_logger(__name__)
VERSION = version("t2-agentic-voice")
# The private provider's queue and timeouts (plan 002's decision log).
QUEUE_SPANS = 512  # spans held while the exporter is slow; one more is dropped and counted
BATCH_SPANS = 128  # spans per export request
DELAY_S = 1.0  # the longest a span sits in the queue before its batch is sent
EXPORT_TIMEOUT_S = 2.0  # one export request, the exporter's own retries included
CLOSE_S = 3.0  # the longest `shutdown` gives the last batch before counting it dropped
# All eight, so none comes from an OTEL_*_LIMIT variable: the SDK's own 128 for the attributes,
# events, links, a span's, an event's and a link's attributes; and a cap on a value's length.
_LIMITS = SpanLimits(128, 128, 128, 128, 128, 128, 8192, 8192)
# All an export request carries, beside Content-Length and Host: no OTEL_* header, no .netrc login.
EXPORT_HEADERS = {
    "Content-Type": "application/x-protobuf",
    "User-Agent": f"t2-agentic-voice/{VERSION}",
}


class SpanQueue(SpanProcessor):
    """The private provider's bounded queue and the worker thread sending it in batches; nothing
    here blocks or raises into the thread that ends a span. Not the SDK's batch processor, which
    counts no drop unless an `OTEL_*` variable says so, and gives a hung exporter 30 s to close."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter
        self._spans: deque[ReadableSpan] = deque()
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._closed = False
        self._failing = False
        self.dropped = 0
        self._size, self._batch, self._delay_s = QUEUE_SPANS, BATCH_SPANS, DELAY_S
        self._close_s = CLOSE_S
        self._worker = threading.Thread(target=self._work, name="t2v-span-export", daemon=True)
        self._worker.start()

    def on_end(self, span: ReadableSpan) -> None:
        with self._lock:
            if self._closed or len(self._spans) >= self._size:
                self.dropped += 1
                return
            self._spans.append(span)
            if len(self._spans) >= self._batch:
                self._ready.set()

    def _work(self) -> None:
        while not self._closed:
            self._ready.wait(self._delay_s)
            self._ready.clear()
            self._drain()
        self._drain()

    def _drain(self) -> None:
        while True:
            with self._lock:
                count = min(self._batch, len(self._spans))
                batch = [self._spans.popleft() for _ in range(count)]
            if not batch:
                return
            self._send(batch)

    def _send(self, batch: list[ReadableSpan]) -> None:
        failure = "failed"
        try:
            sent = self._exporter.export(batch) is SpanExportResult.SUCCESS
        except Exception as error:  # an exporter's failure never reaches the caller
            sent, failure = False, type(error).__qualname__
        if sent:
            self._failing = False
            return
        with self._lock:
            self.dropped += len(batch)
        if not self._failing:  # once per run of failures, by type only: a message may echo data
            self._failing = True
            _log.warning("span_export_failed", spans=len(batch), failure=failure)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._ready.set()
        self._worker.join(self._close_s)
        with self._lock:  # what a hung exporter left queued is dropped, not awaited
            self.dropped += len(self._spans)
            self._spans.clear()
        try:
            self._exporter.shutdown()
        except Exception as error:
            _log.warning("span_exporter_close_failed", failure=type(error).__qualname__)


def private_provider(queue: SpanQueue, project: str | None) -> SdkTracerProvider:
    """The library's own provider, never installed globally, every `OTEL_*` value passed."""
    attributes: dict[str, AnyValue] = {"service.name": "t2-agentic-voice"}
    if project:
        attributes[ResourceAttributes.PROJECT_NAME] = project
    provider = SdkTracerProvider(
        sampler=ParentBased(ALWAYS_ON),
        resource=Resource(attributes),
        span_limits=_LIMITS,
        meter_provider=NoOpMeterProvider(),
    )
    provider.add_span_processor(queue)
    return provider


class ExportSession(requests.Session):
    """The OTLP exporter's own session. Every request carries `EXPORT_HEADERS` alone: the
    exporter adds `OTEL_EXPORTER_OTLP_HEADERS` (or its `_TRACES_` form) under any headers it is
    given (plan 002's decision log), and requests a `.netrc` login."""

    def request(  # type: ignore[override]
        self, method: str, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        """The exporter's headers are replaced before requests checks them, since requests puts
        a header it refuses (one with a line break that the variable's `%0A` decoded) in its
        error, which the exporter logs at ERROR. The exporter passes them as a keyword."""
        kwargs["headers"] = dict(EXPORT_HEADERS)
        return super().request(method, url, **kwargs)

    def prepare_request(self, request: requests.Request) -> requests.PreparedRequest:
        prepared = super().prepare_request(request)
        prepared.headers.clear()  # also drops the .netrc login requests adds here
        prepared.headers.update(EXPORT_HEADERS)
        prepared.prepare_content_length(prepared.body)
        return prepared


def otlp_exporter(endpoint: str) -> OTLPSpanExporter:
    """Plain OTLP over HTTP to `endpoint`, every value the exporter would read from an
    `OTEL_EXPORTER_OTLP_*` variable passed, and its own session. While it is built, the SDK's
    warning about a malformed header variable is dropped: it quotes the value (a token, say),
    and the session sends none of those headers anyway."""

    def hide(record: logging.LogRecord) -> bool:  # a filter of this call's own
        return False

    session = ExportSession()
    parser = logging.getLogger("opentelemetry.util.re")
    parser.addFilter(hide)
    try:
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={},
            timeout=EXPORT_TIMEOUT_S,
            compression=Compression.NoCompression,
            session=session,
            meter_provider=NoOpMeterProvider(),
        )
    finally:
        parser.removeFilter(hide)
    # The exporter sets these from OTEL_EXPORTER_OTLP_*CERTIFICATE and *CLIENT_KEY when no file
    # is passed; requests' own defaults are put back.
    session.verify, session.cert = True, None
    return exporter
