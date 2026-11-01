"""Tracing helpers: the library's own spans, in OpenInference's format, as plain OTLP (D-023).

Built by plan 002's Track C; until then stubs. `Tracing` uses the team's `TracerProvider` when
one is given, otherwise a private one built from `tracing.endpoint`, otherwise none, when every
helper does nothing; it never installs a provider globally, and an exporter that fails never
reaches the caller. Its span helpers take the parent span as an argument, since an implicit
current span does not cross the pipeline's tasks (ARCHITECTURE.md). Every text attribute
passes through the `Redactor`; no audio and no secret is ever exported (the design's 10.1).
Public through the `tracing` facade (D-021).
"""

from __future__ import annotations

from contextlib import AbstractContextManager

from opentelemetry.trace import Span, TracerProvider

from t2_agentic_voice.core.config import Settings

_STUB = "the tracing helpers are built by plan 002's Track C"


class SpeechToTextSpan:
    """One speech-to-text span, open while its request runs."""

    def record(self, *, text: str, language: str | None, billed_seconds: float | None) -> None:
        """What the provider returned: the transcript (only with `tracing.include_transcripts`
        on, and redacted), the language and the billed seconds."""
        raise NotImplementedError(_STUB)


class Tracing:
    """The library's tracing for one app or one run."""

    @classmethod
    def from_settings(
        cls, settings: Settings, *, tracer_provider: TracerProvider | None = None
    ) -> Tracing:
        """Tracing on `tracer_provider` (the team's own) when given; otherwise on a private
        provider sending to `tracing.endpoint`; otherwise off."""
        raise NotImplementedError(_STUB)

    @property
    def dropped_spans(self) -> int:
        """The spans the export queue dropped because it was full or its exporter failed."""
        raise NotImplementedError(_STUB)

    def turn(self, *, session_id: str, name: str = "turn") -> AbstractContextManager[Span]:
        """The span of one turn, or of one golden-set variant: the root of its trace, with
        `session.id` set to `session_id`, so the backend groups one call's (or run's) traces."""
        raise NotImplementedError(_STUB)

    def speech_to_text(
        self, parent: Span, *, model: str, language: str | None, audio_seconds: float
    ) -> AbstractContextManager[SpeechToTextSpan]:
        """A speech-to-text span under `parent`, with the model, the language sent and the
        clip's length; its `record` adds what came back."""
        raise NotImplementedError(_STUB)

    def shutdown(self) -> None:
        """Flush and stop a private provider, within its short timeouts; a team's own provider
        is left as it is."""
        raise NotImplementedError(_STUB)
