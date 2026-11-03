"""Pipecat's failures as the library's own (the design's 10.2; D-031; docs/SECURITY.md, invariant
8): with Pipecat's log lines off (`loguru_policy.py`), a call's failures still show, each as a
library log line that holds no call content, and each once as a public event (core/events.py).
The session sends the public event of every failure it is handed, in its stream's order
(voice/session/io.py's failures; voice/session/report.py's `CallEvents`); this module sends
only that of a failure the session never hears of, a speech bridge's error frame.

- A provider's failure, which a speech bridge sees when a port raises `ProviderError`: the line
  `provider_failed`, with the turn it concerns when there is one. The bridge hands the session
  the turn's failed `Transcribed` or the clause's `ClauseFailed`, and the session emits its
  `ProviderFailed`.
- The call's connection failing (ICE failed, voice's own deadline from offer to connected
  passed, the path dropped after it connected, or the transport unable to write any more): the
  line `transport_failed`. The pipeline hands the session the call's `TransportFailure` at its
  stage, and the session emits its `TransportFailed`.
- Every error frame that reaches the pipeline's source (Pipecat's `on_pipeline_error`): the line
  `pipecat_error`, naming the processor's class, the error's category, whether the processor
  can still work, and the exception's type, never the frame's text, which may quote what was
  said or sent (`Error processing frame: ...`). A transport's error that leaves it unable to
  work ends the call (`TransportFailure` at `media`); the rest are logged, and a speech
  bridge's is the line `provider_failed` too and a `ProviderFailed` naming no turn, emitted
  here, since no event of the session's carries it.

Public events go to the runtime's sink, which returns at once and never raises
(voice/session/io.py's `EventSink`).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pipecat.frames.frames import ErrorFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport

from t2_agentic_voice.core.errors import ProviderError, ProviderErrorKind
from t2_agentic_voice.core.events import CallId, ProviderFailed, TransportStage
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.session.io import Clock, EventSink

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class FailureReport:
    """Where one call's failures are reported, for `call_id`: a log line for each, and the
    public event of a speech bridge's error frame, which the session never hears of, sent to
    `emit` and stamped on `clock`'s time of day. The session emits the rest."""

    call_id: CallId
    emit: EventSink
    clock: Clock

    def provider_failed(
        self,
        service: str,
        kind: ProviderErrorKind,
        retryable: bool,
        *,
        turn_id: int | None = None,
    ) -> None:
        """A provider failed a request of `service` (`speech_to_text`, `text_to_speech`): its
        line. The session emits the `ProviderFailed`, from the event the bridge hands it."""
        log.warning(
            "provider_failed",
            call_id=self.call_id,
            service=service,
            kind=kind,
            retryable=retryable,
            turn_id=turn_id,
        )

    def transport_failed(self, stage: TransportStage) -> None:
        """The call's connection failed at `stage`: its line. The session emits the
        `TransportFailed`, from the `TransportFailure` the pipeline hands it."""
        log.warning("transport_failed", call_id=self.call_id, stage=stage)

    def error_frame(
        self, frame: ErrorFrame, *, speech: Collection[tuple[FrameProcessor, str]]
    ) -> TransportStage | None:
        """Report an error frame that reached the pipeline's source: logged with no content; a
        speech bridge's (one of `speech`, each with the port it serves) its `provider_failed`
        line too and a `ProviderFailed` emitted here, naming no turn. The stage at which the
        call's connection failed when the error left a transport unable to work, which ends
        the call (its caller reports `transport_failed`); None otherwise."""
        processor = frame.processor
        exception = frame.exception
        usable = processor.is_usable if processor is not None else True
        log.error(
            "pipecat_error",
            call_id=self.call_id,
            processor=type(processor).__name__ if processor is not None else None,
            category=frame.category.value if frame.category is not None else None,
            usable=usable,
            error=type(exception).__name__ if exception is not None else None,
        )
        if isinstance(processor, BaseInputTransport | BaseOutputTransport):
            return None if usable else "media"
        for bridge, service in speech:
            if processor is bridge and isinstance(exception, ProviderError):
                self._bridge_failed(service, exception.kind, exception.retryable)
            elif processor is bridge:
                self._bridge_failed(service, "server_error", False)
        return None

    def _bridge_failed(self, service: str, kind: ProviderErrorKind, retryable: bool) -> None:
        """A speech bridge's error frame: its line and its `ProviderFailed`, naming no turn."""
        self.provider_failed(service, kind, retryable)
        at = self.clock.wall()
        failed = ProviderFailed(
            call_id=self.call_id, turn_id=None, at=at, kind=kind, retryable=retryable
        )
        self.emit(failed)
