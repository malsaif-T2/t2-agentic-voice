"""Tracing helpers: the library's own spans, in OpenInference's format, as plain OTLP (D-023).

`Tracing` uses the team's `TracerProvider` when one is given, otherwise a private one sending
to `tracing.endpoint`, otherwise none, when every helper does nothing; it never installs a
provider globally. Its span helpers take the parent span as an argument, since an implicit
current span does not cross the pipeline's tasks (ARCHITECTURE.md). Every text attribute of
every span they make passes through the `Redactor`; no bytes (audio) and no exception's message
are ever exported (the design's 10.1). Public through the `tracing` facade (D-021).

A private provider's spans go through a bounded queue to a worker thread, so an exporter that
fails or hangs never reaches the caller; a span that cannot be queued or sent is counted. Every
value the SDK and its OTLP exporter would read from an `OTEL_*` variable is passed (plan 002's
decision log): a sampler, a `Resource` built directly, the span limits, a no-op meter provider,
and the exporter's endpoint, timeout, compression and own `requests.Session`, which sends only
the headers OTLP needs and verifies with requests' defaults. `OTEL_SDK_DISABLED` and
`OTEL_PYTHON_CONTEXT` are read whatever is passed (TD-005).
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from importlib.metadata import version

import requests
from openinference.semconv.resource import ResourceAttributes
from openinference.semconv.trace import (
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
)
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, SpanProcessor
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from opentelemetry.trace import (
    NoOpTracer,
    Span,
    SpanContext,
    Status,
    StatusCode,
    Tracer,
    TracerProvider,
    set_span_in_context,
)
from opentelemetry.util.types import AnyValue, Attributes

from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.redaction import Redactor

_log = get_logger(__name__)
_SCOPE = "t2_agentic_voice"
_VERSION = version("t2-agentic-voice")
# The private provider's queue and timeouts (plan 002's decision log).
_QUEUE_SPANS = 512  # spans held while the exporter is slow; one more is dropped and counted
_BATCH_SPANS = 128  # spans per export request
_DELAY_S = 1.0  # the longest a span sits in the queue before its batch is sent
_EXPORT_TIMEOUT_S = 2.0  # one export request, the exporter's own retries included
_CLOSE_S = 3.0  # the longest `shutdown` gives the last batch before counting it dropped
# All eight limits, so none comes from an OTEL_*_LIMIT variable: the SDK's own 128 for the
# attributes, events and links (then the span's, an event's and a link's attributes), and a cap
# on a value's length.
_LIMITS = SpanLimits(128, 128, 128, 128, 128, 128, 8192, 8192)
# The only headers an export request carries (requests adds Content-Length and the transport
# its Host): neither OTEL_EXPORTER_OTLP_HEADERS nor a .netrc login reaches the backend.
_EXPORT_HEADERS = {
    "Content-Type": "application/x-protobuf",
    "User-Agent": f"t2-agentic-voice/{_VERSION}",
}
_ERROR_TYPE = "error.type"
_STT_AUDIO_SECONDS = "stt.audio_seconds"
_STT_BILLED_SECONDS = "stt.billed_seconds"
_STT_LANGUAGE_SENT = "stt.language_sent"
_STT_LANGUAGE = "stt.language"


class _RedactedSpan(Span):
    """A span whose every text value passes through the `Redactor` before it is set. A bytes
    value (audio, say), a mapping and a nested sequence are dropped, and an exception is
    recorded by its type alone, since its message may hold a secret or what was said."""

    def __init__(self, span: Span, redact: Redactor) -> None:
        self._span = span
        self._redact = redact

    def _clean(self, value: AnyValue) -> AnyValue:
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, bool | int | float):
            return value
        if isinstance(value, list | tuple) and all(
            isinstance(item, str | bool | int | float) for item in value
        ):
            return [self._clean(item) for item in value]
        return None

    def _attributes(self, attributes: Attributes) -> dict[str, AnyValue]:
        cleaned = {key: self._clean(value) for key, value in (attributes or {}).items()}
        return {key: value for key, value in cleaned.items() if value is not None}

    def get_span_context(self) -> SpanContext:
        return self._span.get_span_context()

    def is_recording(self) -> bool:
        return self._span.is_recording()

    def end(self, end_time: int | None = None) -> None:
        self._span.end(end_time)

    def set_attributes(self, attributes: Mapping[str, AnyValue]) -> None:
        self._span.set_attributes(self._attributes(attributes))

    def set_attribute(self, key: str, value: AnyValue) -> None:
        self.set_attributes({key: value})

    def add_event(
        self, name: str, attributes: Attributes = None, timestamp: int | None = None
    ) -> None:
        self._span.add_event(self._redact(name), self._attributes(attributes), timestamp)

    def add_link(self, context: SpanContext, attributes: Attributes = None) -> None:
        self._span.add_link(context, self._attributes(attributes))

    def update_name(self, name: str) -> None:
        self._span.update_name(self._redact(name))

    def set_status(self, status: Status | StatusCode, description: str | None = None) -> None:
        if isinstance(status, Status):
            description = status.description
            status = status.status_code
        self._span.set_status(Status(status, description and self._redact(description)))

    def record_exception(
        self,
        exception: BaseException,
        attributes: Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        kind = {**(attributes or {}), "exception.type": type(exception).__qualname__}
        self.add_event("exception", kind, timestamp)


class SpeechToTextSpan:
    """One speech-to-text span, open while its request runs."""

    def __init__(self, span: Span, *, include_transcripts: bool) -> None:
        self._span = span
        self._include_transcripts = include_transcripts

    def record(self, *, text: str, language: str | None, billed_seconds: float | None) -> None:
        """What the provider returned: the transcript (only with `tracing.include_transcripts`
        on, and redacted), the language and the billed seconds."""
        attributes: dict[str, AnyValue] = {}
        if self._include_transcripts:
            attributes[SpanAttributes.OUTPUT_VALUE] = text
            attributes[SpanAttributes.OUTPUT_MIME_TYPE] = OpenInferenceMimeTypeValues.TEXT.value
        if language is not None:
            attributes[_STT_LANGUAGE] = language
        if billed_seconds is not None:
            attributes[_STT_BILLED_SECONDS] = billed_seconds
        self._span.set_attributes(attributes)


class Tracing:
    """The library's tracing for one app or one run. Built with no argument, it is off."""

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider | None = None,
        exporter: SpanExporter | None = None,
        project: str | None = None,
        redactor: Redactor | None = None,
        include_transcripts: bool = True,
    ) -> None:
        """Tracing on `tracer_provider` (the team's own, left as it is), or on a private
        provider sending to `exporter` through the bounded queue, filed under `project`, or off
        when given neither; `redactor` runs on every text value, and `include_transcripts`
        says whether a transcript goes in its span."""
        if tracer_provider is not None and exporter is not None:
            raise ValueError("give a tracer provider or an exporter, not both")
        self._redact = redactor or Redactor([])
        self._include_transcripts = include_transcripts
        self._provider: SdkTracerProvider | None = None
        self._queue: _Queue | None = None
        self._tracer: Tracer = NoOpTracer()
        if tracer_provider is not None:
            self._tracer = tracer_provider.get_tracer(_SCOPE, _VERSION)
        elif exporter is not None:
            self._queue = _Queue(exporter)
            self._provider = _private_provider(self._queue, project and self._redact(project))
            self._tracer = self._provider.get_tracer(_SCOPE, _VERSION)
            if isinstance(self._tracer, NoOpTracer):
                _log.warning("tracing_disabled_by_sdk", fix="unset OTEL_SDK_DISABLED")

    @classmethod
    def from_settings(
        cls, settings: Settings, *, tracer_provider: TracerProvider | None = None
    ) -> Tracing:
        """Tracing on `tracer_provider` (the team's own) when given; otherwise on a private
        provider sending to `tracing.endpoint`; otherwise off."""
        config = settings.tracing
        exporter = None
        if tracer_provider is None and config.endpoint is not None:
            exporter = _otlp_exporter(config.endpoint)
        return cls(
            tracer_provider=tracer_provider,
            exporter=exporter,
            project=config.project,
            redactor=Redactor(config.redact),
            include_transcripts=config.include_transcripts,
        )

    @property
    def dropped_spans(self) -> int:
        """The spans the export queue dropped because it was full or its exporter failed, and
        those still queued when `shutdown` gave up or ended after it."""
        return 0 if self._queue is None else self._queue.dropped

    def turn(self, *, session_id: str, name: str = "turn") -> AbstractContextManager[Span]:
        """The span of one turn, or of one golden-set variant: the root of its trace, with
        `session.id` set to `session_id`, so the backend groups one call's (or run's) traces."""
        attributes: dict[str, AnyValue] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            SpanAttributes.SESSION_ID: session_id,
        }
        return self._span(name, Context(), attributes)

    def speech_to_text(
        self, parent: Span, *, model: str, language: str | None, audio_seconds: float
    ) -> AbstractContextManager[SpeechToTextSpan]:
        """A speech-to-text span under `parent`, with the model, the language sent and the
        clip's length; its `record` adds what came back."""
        attributes: dict[str, AnyValue] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
            SpanAttributes.LLM_MODEL_NAME: model,
            _STT_AUDIO_SECONDS: audio_seconds,
        }
        if language is not None:
            attributes[_STT_LANGUAGE_SENT] = language
        return self._stt(parent, attributes)

    @contextmanager
    def _stt(self, parent: Span, attributes: dict[str, AnyValue]) -> Iterator[SpeechToTextSpan]:
        with self._span("speech_to_text", set_span_in_context(parent), attributes) as span:
            yield SpeechToTextSpan(span, include_transcripts=self._include_transcripts)

    @contextmanager
    def _span(self, name: str, parent: Context, attributes: dict[str, AnyValue]) -> Iterator[Span]:
        """A span under `parent`, ended when the block ends. An exception leaving the block
        marks it an error, by the exception's type alone, and goes on to the caller."""
        span = _RedactedSpan(self._tracer.start_span(self._redact(name), parent), self._redact)
        span.set_attributes(attributes)
        try:
            yield span
        except BaseException as error:
            span.set_attribute(_ERROR_TYPE, type(error).__qualname__)
            span.set_status(StatusCode.ERROR, type(error).__qualname__)
            raise
        finally:
            span.end()

    def shutdown(self) -> None:
        """Flush and close a private provider, within its short timeouts; a team's own provider
        is left as it is."""
        if self._provider is not None:
            self._provider.shutdown()


class _Queue(SpanProcessor):
    """The private provider's bounded queue and its worker thread, which sends the spans in
    batches. Nothing here blocks or raises into the thread that ends a span, and a span that
    cannot be queued or sent is counted. The SDK's batch processor is not used: it counts
    nothing it drops unless an `OTEL_*` variable turns its metrics on, and its own shutdown
    gives a hung exporter 30 seconds."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter
        self._spans: deque[ReadableSpan] = deque()
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._closed = False
        self._failing = False
        self.dropped = 0
        self._size, self._batch, self._delay_s = _QUEUE_SPANS, _BATCH_SPANS, _DELAY_S
        self._close_s = _CLOSE_S
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


def _private_provider(queue: _Queue, project: str | None) -> SdkTracerProvider:
    """A provider of the library's own, never installed globally, with every value the SDK
    would read from an `OTEL_*` variable passed."""
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


class _ExportSession(requests.Session):
    """The OTLP exporter's own session. Every request carries `_EXPORT_HEADERS` alone: the
    exporter adds `OTEL_EXPORTER_OTLP_HEADERS` (or its `_TRACES_` form) under any headers it is
    given (plan 002's decision log), and requests a `.netrc` login."""

    def prepare_request(self, request: requests.Request) -> requests.PreparedRequest:
        prepared = super().prepare_request(request)
        prepared.headers.clear()
        prepared.headers.update(_EXPORT_HEADERS)
        prepared.prepare_content_length(prepared.body)
        return prepared


def _otlp_exporter(endpoint: str) -> OTLPSpanExporter:
    """Plain OTLP over HTTP to `endpoint`, every value the exporter would read from an
    `OTEL_EXPORTER_OTLP_*` variable passed, and its session given."""
    session = _ExportSession()
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={},
        timeout=_EXPORT_TIMEOUT_S,
        compression=Compression.NoCompression,
        session=session,
        meter_provider=NoOpMeterProvider(),
    )
    # The exporter sets these from OTEL_EXPORTER_OTLP_*CERTIFICATE and *CLIENT_KEY when no file
    # is passed; requests' own defaults are put back.
    session.verify, session.cert = True, None
    return exporter
