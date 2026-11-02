"""The phrase cache (adapters/phrase_cache.py). Plan 003's Track B builds it and replaces this
file's stub test with its own."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from t2_agentic_voice.adapters.phrase_cache import PhraseCache
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.session.io import Phrases


def test_the_phrase_cache_is_a_stub_until_track_b(settings: VoiceSettings, tmp_path: Path) -> None:
    tts = cast(TextToSpeech, object())
    voices = TtsSettings().languages
    builds: list[Callable[[], object]] = [
        lambda: PhraseCache(tts, folder=tmp_path, voices=voices),
        lambda: PhraseCache.from_settings(settings, tts, folder=tmp_path),
    ]
    for build in builds:
        with pytest.raises(NotImplementedError, match="Track B"):
            build()
    stub = PhraseCache.__new__(PhraseCache)  # the methods' stubs, past the constructor's
    phrases: Phrases = stub  # the session's view of it: mypy checks the protocol's shape
    with pytest.raises(NotImplementedError, match="Track B"):
        asyncio.run(stub.declare([("I heard:", "en")]))
    with pytest.raises(NotImplementedError, match="Track B"):
        phrases.audio("I heard:", language="en")
