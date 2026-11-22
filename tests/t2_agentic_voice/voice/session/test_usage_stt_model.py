"""The model a call's usage names for its speech-to-text (voice/session/usage.py, books.py,
turn_book.py; D-140, which fixed the old debt of naming `stt.model` whatever the provider): the
model the composition root hands the call's setup, in its usage, its turn's speech-to-text span
and its trace's resource; `stt.model` when the setup names none, as a test's or a text call's."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from openinference.semconv.trace import SpanAttributes
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.core.tracing_tts import MODELS
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    greeted,
    report,
    spans,
    turn,
)

WHISPER = "whisper-large-v3"


@pytest.fixture
def settings(settings: VoiceSettings) -> VoiceSettings:
    """The suite's settings with Groq's Orpheus speaking, as test_call_report.py's."""
    return settings.model_copy(update={"tts": TtsSettings(provider="groq")})


def test_the_usage_and_the_traces_name_the_model_that_heard_the_call(
    settings: VoiceSettings,
) -> None:
    """A call whose setup names the model its turns are heard by (Scribe's, as the runtime names
    it) reports its usage, its turn's speech-to-text span and its resource under
    that model, never `stt.model`'s Whisper; a setup that names none keeps `stt.model`."""
    io, _ = call(settings)
    exporter = InMemorySpanExporter()
    setup = dataclasses.replace(io.setup, stt_model="scribe_v3", tracing=Tracing(exporter=exporter))
    session = CallSession(setup, io.commands)
    io.attach(session)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    usage = report(io).usage
    assert usage[0].model == "scribe_v3" and WHISPER not in [u.model for u in usage]
    found = spans(session, exporter)
    stt = next(s for s in found if s.name == "speech_to_text").attributes or {}
    assert stt[SpanAttributes.LLM_MODEL_NAME] == "scribe_v3"
    root = next(s for s in found if s.parent is None).attributes or {}
    assert next(iter(root[MODELS])) == "scribe_v3"  # type: ignore[arg-type]
    assert setup.heard_model == "scribe_v3" and io.setup.heard_model == WHISPER
