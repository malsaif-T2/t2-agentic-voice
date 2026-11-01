"""Tracing helpers: the library's own spans, in OpenInference's format, as plain OTLP (D-023).

`Tracing` uses the team's `TracerProvider` when given, otherwise a private one sending to
`tracing.endpoint`, otherwise none; it never installs a provider globally. Its span helpers take
the parent span as an argument, since an implicit current span does not cross the pipeline's
tasks (ARCHITECTURE.md). Every text, an attribute's key included, passes through the
`Redactor`; no bytes (audio) and no exception's message are exported (the design's 10.1).
Public through the `tracing` facade (D-021). A private provider's spans go through a bounded
queue to a worker thread, so a failing or hung exporter never reaches the caller, and every
value the SDK and its exporter would read from an `OTEL_*` variable is passed
(`core/tracing_export.py`, plan 002's decision log); `OTEL_SDK_DISABLED` and
`OTEL_PYTHON_CONTEXT` are read whatever is passed (TD-005).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager

from openinference.semconv.trace import (
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
)
from opentelemetry.context import Context
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
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
from t2_agentic_voice.core.tracing_export import (
    VERSION,
    SpanQueue,
    otlp_exporter,
    private_provider,
)

_log = get_logger(__name__)
_SCOPE = "t2_agentic_voice"
_STT_AUDIO_SECONDS = "stt.audio_seconds"
_STT_BILLED_SECONDS = "stt.billed_seconds"
_STT_LANGUAGE_SENT = "stt.language_sent"
_STT_LANGUAGE = "stt.language"


class _RedactedSpan(Span):
    """A span whose every text, an attribute's key as well as its value, passes through the
    `Redactor` before it is set. A bytes value (audio, say), a mapping and a nested sequence are
    dropped, and an exception is recorded by its type alone, since its message may hold a secret
    or what was said."""

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
        """Each key and each text value redacted; a value of another kind dropped."""
        items = (attributes or {}).items()
        cleaned = {self._redact(key): self._clean(value) for key, value in items}
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
        """Tracing on `tracer_provider` (the team's own, left as it is), or on a private provider
        sending to `exporter` through the bounded queue, filed under `project`, or off; `redactor`
        runs on every text value, and `include_transcripts` keeps or drops the transcript."""
        if tracer_provider is not None and exporter is not None:
            raise ValueError("give a tracer provider or an exporter, not both")
        self._redact = redactor or Redactor([])
        self._include_transcripts = include_transcripts
        self._provider: SdkTracerProvider | None = None
        self._queue: SpanQueue | None = None
        self._tracer: Tracer = NoOpTracer()
        if tracer_provider is not None:
            self._tracer = tracer_provider.get_tracer(_SCOPE, VERSION)
        elif exporter is not None:
            self._queue = SpanQueue(exporter)
            self._provider = private_provider(self._queue, project and self._redact(project))
            self._tracer = self._provider.get_tracer(_SCOPE, VERSION)
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
            exporter = otlp_exporter(config.endpoint)
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
            span.set_attribute("error.type", type(error).__qualname__)
            span.set_status(StatusCode.ERROR, type(error).__qualname__)
            raise
        finally:
            span.end()

    def shutdown(self) -> None:
        """Flush and close a private provider, within its short timeouts; a team's own provider
        is left as it is."""
        if self._provider is not None:
            self._provider.shutdown()
