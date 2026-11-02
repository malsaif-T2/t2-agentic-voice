"""voice's entry point (voice/calls.py). Plan 003's Track E builds it and replaces this file's stub
test with its own; api's tests use the fake entry point instead."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.calls import Calls, CallsFactory, Candidate, VoiceCalls
from t2_agentic_voice.voice.session.io import Phrases

if TYPE_CHECKING:  # as voice/calls.py names them: no Pipecat is imported
    from pipecat.audio.turn.base_turn_analyzer import BaseTurnAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADAnalyzer

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
END = Candidate(candidate="", sdp_mid="0", sdp_mline_index=0)  # the end of candidates


def test_voices_entry_point_is_a_stub_until_track_e(settings: VoiceSettings) -> None:
    built: CallsFactory = VoiceCalls  # mypy checks that the runtime can build it
    with pytest.raises(NotImplementedError, match="Track E"):
        built(
            agent=VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")]),
            settings=settings,
            stt=cast(SpeechToText, object()),
            tts=cast(TextToSpeech, object()),
            phrases=cast(Phrases, object()),
            tracing=Tracing(),
            emit=lambda event: None,
        )
    with pytest.raises(NotImplementedError, match="Track E"):  # a test's detectors (step 16)
        VoiceCalls(
            agent=VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")]),
            settings=settings,
            stt=cast(SpeechToText, object()),
            tts=cast(TextToSpeech, object()),
            phrases=cast(Phrases, object()),
            tracing=Tracing(),
            emit=lambda event: None,
            speech_detector=lambda: cast("VADAnalyzer", object()),
            turn_analyzer=lambda: cast("BaseTurnAnalyzer", object()),
        )
    stub = VoiceCalls.__new__(VoiceCalls)  # the methods' stubs, past the constructor's
    calls: Calls = stub  # mypy checks the protocol's shape
    steps: list[Callable[[], object]] = [
        lambda: asyncio.run(calls.start()),
        lambda: asyncio.run(calls.answer("call-1", "v=0", caller=CALLER, consent=CONSENT)),
        lambda: asyncio.run(calls.add_candidates("call-1", [END])),
        lambda: calls.phase("call-1"),
        lambda: asyncio.run(calls.end("call-1")),
        lambda: asyncio.run(calls.aclose()),
    ]
    for step in steps:
        with pytest.raises(NotImplementedError, match="Track E"):
            step()
