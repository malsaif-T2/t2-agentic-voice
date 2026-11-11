"""Two calls of a talker agent saying the same reply over one clause cache (testing/audio_call.py,
adapters/clause_cache.py; plan 007's run T arm): the real file-fed pipeline with the tests' tone
detector and a turn analyzer that ends each turn at its first pause, a talker of the test's that
answers each turn with the same clause; the first call sends that clause's request, the second
none for it. The requests are counted, not the times: `AudioCall` runs on the system clock."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path

import pytest
from t2_agentic_voice.adapters.clause_cache import ClauseCache
from t2_agentic_voice.agent.talker import (
    ReplyDone,
    ReplyScope,
    SpokenClause,
    TalkerCall,
    TalkerEvent,
)
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.evals import AudioCall, TurnReplay
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.talkers import TalkerFactory

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

AGENT = VoiceAgent(
    name="replayed", languages=[Language.english(greeting="Hi.")], instructions="Be brief."
)
CLAUSE = "Your ticket is open."


class _Talker:
    """One clause, the same for every turn."""

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        yield SpokenClause(text=CLAUSE, language="en")
        yield ReplyDone()


def _factory(call: TalkerCall, clock: Clock) -> _Talker:
    return _Talker()


class _Replay(AudioCall):
    def _talkers(self) -> TalkerFactory | None:  # the test's talker, not the library's
        return _factory


def test_the_second_call_says_the_clause_from_the_cache_with_no_request(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    fake = FakeTextToSpeech(seconds_per_char=0.03)
    cache = ClauseCache(
        fake,
        folder=tmp_path / "clauses",
        voices=settings.tts.languages,
        trim_silence=False,
        max_mb=8,
    )
    stt = FakeSpeechToText(["where is my ticket"] * 2)
    replay = _Replay(settings=settings, stt=stt, tts=cache, agent=AGENT)
    hold_s = settings.turns.complete_hold_ms / 1000
    asked: list[int] = []

    async def run() -> list[TurnReplay]:
        await cache.open()
        await replay.start()
        found: list[TurnReplay] = []
        try:
            for _ in range(2):
                clip = AudioClip(pcm16=tone(0.5, 16_000))
                found.append(
                    await replay.turn(
                        clip,
                        greeting=("Hello there.",),
                        language="en",
                        lead_s=0.5,
                        tail_s=2.0 + hold_s,
                        speech_end_ms=500.0,
                    )
                )
                await cache._written()
                asked.append(fake.calls.count((CLAUSE, "en")))
        finally:
            await replay.aclose()
            await cache.aclose()
        return found

    first, second = asyncio.run(asyncio.wait_for(run(), timeout=60))
    assert asked == [1, 1]  # the first call's request, and none in the second
    assert first.first_audible_ms is not None and second.first_audible_ms is not None
    counts = cache.counts()
    assert counts.hits == 1 and counts.kept >= 1
    assert not fake.closed  # whoever built it closes it
