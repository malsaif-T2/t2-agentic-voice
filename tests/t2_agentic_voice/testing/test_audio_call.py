"""The replay of a clip over a reply (testing/audio_call.py, the design's 9.5): its results are
frozen, and the replay a stub until plan 005's Track E builds it, whose tests replay made-up clips
with fake speech ports, never a request."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.evals import AudioCall, OverlapReplay, OverlapRequest

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone


def test_a_replays_results_are_frozen() -> None:
    request = OverlapRequest(part="window", sent_ms=1750.0, audio_s=0.75, text="made-up")
    replay = OverlapReplay(opened=True, action="stop", kind="stop", requests=(request,))
    with pytest.raises(ValidationError):
        replay.action = "go_on"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        OverlapRequest.model_validate(request.model_dump() | {"part": "middle"})
    assert (replay.decided_by, replay.stop_ms, OverlapReplay(opened=False).requests) == (
        None,
        None,
        (),
    )


def test_the_replay_is_a_stub_until_it_is_built(settings: VoiceSettings) -> None:
    stt, tts = FakeSpeechToText(), FakeTextToSpeech()
    replay = AudioCall(settings=settings, stt=stt, tts=tts)
    assert (replay.settings, replay.stt, replay.tts) == (settings, stt, tts)
    clip = AudioClip(pcm16=tone(0.5, 16_000), sample_rate=16_000)

    async def call() -> None:
        with pytest.raises(NotImplementedError, match="Track E"):
            await replay.start()
        with pytest.raises(NotImplementedError, match="Track E"):
            await replay.over_reply(
                clip, reply=("a made-up clause",), language="en", at_s=1.0, tail_s=4.5
            )
        with pytest.raises(NotImplementedError, match="Track E"):
            await replay.aclose()

    asyncio.run(call())
