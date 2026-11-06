"""A clip replayed as a turn through an agent's talker (testing/audio_call.py's `AudioCall.turn`,
testing/turn_replay.py; plan 006's time to first audio): the real file-fed pipeline with the
tests' tone detector and a turn analyzer that ends each turn at its first pause, the early start
on, a talker of the test's that says the agent's progress line, works, then answers; the reply's
first audible frame and the progress line's, apart, from the clip's start and from its labelled
end of speech, with the session's own times of the turn."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import partial

import pytest
from t2_agentic_voice.agent.talker import (
    ProgressDue,
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

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

AGENT = VoiceAgent(
    name="replayed",
    languages=[Language.english(greeting="Hi.", progress={"looking": "One moment please."})],
    instructions="Answer briefly.",
)


class _Talker:
    """A progress line, half a second's work in the reply's scope, then one clause."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.turns: list[TalkerTurn] = []

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        self.turns.append(turn)
        yield ProgressDue(tool="search_help", key="looking", language="en")
        await scope.start(self.clock.sleep(0.5), name="search")
        yield SpokenClause(text="Your ticket is open.", language="en")
        yield ReplyDone()


def test_a_clip_replayed_as_a_turn_reads_its_reply_and_its_progress_line_apart(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    talkers: list[_Talker] = []

    def factory(call: TalkerCall, clock: Clock) -> _Talker:
        talkers.append(_Talker(clock))
        return talkers[-1]

    tts = FakeTextToSpeech(seconds_per_char=0.03)
    replay = AudioCall(
        settings=settings,
        stt=FakeSpeechToText(["where is my ticket"] * 2),
        tts=tts,
        agent=AGENT,
        talker=factory,
    )
    hold_s = settings.turns.complete_hold_ms / 1000

    async def run() -> TurnReplay:
        await replay.start()
        try:
            clip = AudioClip(pcm16=tone(0.5, 16_000))
            return await replay.turn(
                clip,
                greeting=("Hello there.",),
                language="en",
                lead_s=0.5,
                tail_s=3.0 + hold_s,
                speech_end_ms=500.0,
            )
        finally:
            await replay.aclose()

    found = asyncio.run(asyncio.wait_for(run(), timeout=60))
    (talker,) = talkers
    assert [t.words for t in talker.turns] == ["where is my ticket"]
    assert ("One moment please.", "en") in tts.calls  # said once, at the start
    assert found.progress_audible_ms is not None and found.first_audible_ms is not None
    assert found.progress_audible_ms < found.first_audible_ms
    assert found.ttfa_ms == pytest.approx(found.first_audible_ms - 500.0)
    assert found.progress_ms == pytest.approx(found.progress_audible_ms - 500.0)
    assert found.times is not None and found.times.ttfa_ms is not None
    assert found.times.progress_ms is not None and found.times.progress_ms < found.times.ttfa_ms
