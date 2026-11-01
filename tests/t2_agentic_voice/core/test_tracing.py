"""The tracing helpers. Plan 002's Track C builds them and replaces this file's stub test."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from opentelemetry.trace import INVALID_SPAN
from t2_agentic_voice.core.config import Settings
from t2_agentic_voice.core.tracing import SpeechToTextSpan, Tracing


def test_the_tracing_helpers_are_stubs_until_track_c(settings: Settings) -> None:
    tracing = Tracing()
    calls: list[Callable[[], object]] = [
        lambda: Tracing.from_settings(settings),
        lambda: tracing.dropped_spans,
        lambda: tracing.turn(session_id="run"),
        lambda: tracing.speech_to_text(
            INVALID_SPAN, model="whisper-large-v3", language="ar", audio_seconds=1.0
        ),
        tracing.shutdown,
        lambda: SpeechToTextSpan().record(text="", language=None, billed_seconds=None),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track C"):
            call()
