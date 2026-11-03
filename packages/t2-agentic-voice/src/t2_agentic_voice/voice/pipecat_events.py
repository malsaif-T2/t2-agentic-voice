"""Pipecat's failures as the library's own (the design's 10.2; D-031; docs/SECURITY.md, invariant
8): with Pipecat's log lines off (`loguru_policy.py`), a call's failures still show, each as a
library log line that holds no call content and as a public event (core/events.py).

- A provider's failure, which a speech bridge sees when a port raises `ProviderError`, or an
  error frame a speech bridge pushes: `ProviderFailed`, with the turn it concerns when there is
  one, and the line `provider_failed`.
- The call's connection failing (ICE failed, voice's own deadline from offer to connected
  passed, the path dropped after it connected, or the transport unable to write any more):
  `TransportFailed` at its stage, and the line `transport_failed`.
- Every error frame that reaches the pipeline's source (Pipecat's `on_pipeline_error`): the line
  `pipecat_error`, naming the processor's class, the error's category, whether the processor
  can still work, and the exception's type, never the frame's text, which may quote what was
  said or sent (`Error processing frame: ...`). A transport's error that leaves it unable to
  work ends the call (`TransportFailure` at `media`); the rest are logged, and a speech
  bridge's is a `ProviderFailed` too.

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
from t2_agentic_voice.core.events import CallId, ProviderFailed, TransportFailed, TransportStage
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.voice.session.io import Clock, EventSink

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class FailureReport:
    """Where one call's failures are reported: its log lines and public events, for `call_id`,
    stamped on `clock`'s time of day."""

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
        """A provider failed a request of `service` (`speech_to_text`, `text_to_speech`)."""
        log.warning(
            "provider_failed",
            call_id=self.call_id,
            service=service,
            kind=kind,
            retryable=retryable,
            turn_id=turn_id,
        )
        failed = ProviderFailed(
            call_id=self.call_id,
            turn_id=turn_id,
            at=self.clock.wall(),
            kind=kind,
            retryable=retryable,
        )
        self.emit(failed)

    def transport_failed(self, stage: TransportStage) -> None:
        """The call's connection failed at `stage`."""
        log.warning("transport_failed", call_id=self.call_id, stage=stage)
        self.emit(TransportFailed(call_id=self.call_id, at=self.clock.wall(), stage=stage))

    def error_frame(
        self, frame: ErrorFrame, *, speech: Collection[tuple[FrameProcessor, str]]
    ) -> TransportStage | None:
        """Report an error frame that reached the pipeline's source: logged with no content; a
        speech bridge's (one of `speech`, each with the port it serves) a `ProviderFailed`
        too. The stage at which the call's connection failed when the error left a transport
        unable to work, which ends the call (its caller reports `transport_failed`); None
        otherwise."""
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
                self.provider_failed(service, exception.kind, exception.retryable)
            elif processor is bridge:
                self.provider_failed(service, "server_error", False)
        return None
