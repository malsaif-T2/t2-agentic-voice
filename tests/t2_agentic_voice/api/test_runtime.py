"""The runtime (api/runtime.py). Plan 003's Track F builds it and replaces this file's stub test
with its own, against the fake voice entry point; `Providers.replace` is built already."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

import pytest
from t2_agentic_voice.api.runtime import Providers, VoiceRuntime
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallEnded
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.calls import Calls, VoiceCalls

from tests.t2_agentic_voice.fakes import FakeCalls

AGENT = VoiceAgent(name="echo", languages=[Language.english(greeting="Hello there.")])


def test_the_runtime_is_a_stub_until_track_f(settings: VoiceSettings) -> None:
    with pytest.raises(NotImplementedError, match="Track F"):
        VoiceRuntime(AGENT, settings=settings)
    with pytest.raises(NotImplementedError, match="Track F"):
        Providers.from_settings(settings)
    stub = VoiceRuntime.__new__(VoiceRuntime)  # the methods' stubs, past the constructor's
    calls: list[Callable[[], object]] = [
        lambda: stub.lifespan(object()),
        stub.router,
        lambda: stub.on(CallEnded),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError, match="Track F"):
            call()


def test_a_test_gives_the_runtime_its_calls(settings: VoiceSettings) -> None:
    """Track F's tests give the fake entry point through `_calls` (mypy checks that a function
    returning `FakeCalls` fits it); the runtime's own default is `VoiceCalls`."""
    fake = FakeCalls()

    def calls(**_: object) -> Calls:
        return fake

    with pytest.raises(NotImplementedError, match="Track F"):
        VoiceRuntime(AGENT, settings=settings, _calls=calls)
    default = inspect.signature(VoiceRuntime).parameters["_calls"]
    assert (default.kind, default.default) == (inspect.Parameter.KEYWORD_ONLY, VoiceCalls)


def test_providers_replace_only_what_is_given() -> None:
    stt, tts = cast(SpeechToText, object()), cast(TextToSpeech, object())
    other_stt, other_tts = cast(SpeechToText, object()), cast(TextToSpeech, object())
    providers = Providers(stt=stt, tts=tts)
    assert providers.replace() == providers
    assert providers.replace(stt=other_stt) == Providers(stt=other_stt, tts=tts)
    assert providers.replace(tts=other_tts) == Providers(stt=stt, tts=other_tts)
