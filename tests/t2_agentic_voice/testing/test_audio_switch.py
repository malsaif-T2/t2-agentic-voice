"""A scripted audio call that follows the caller into the other language, under
`stt.live_language = "detected"` (D-038's amendment): the real file-fed pipeline
(testing/audio_call.py's `AudioCall`) with the tests' tone detector and a turn analyzer that ends
each turn at its first pause, a Saudi call of an agent of Arabic and English, three turns in one
clip, against a fake Whisper that writes each request in the language it is told, or, told none,
in the one it detects. A long "yes" heard as English moves nothing; a long English question
moves the call, the talker hears its English words; the next short turn goes once, in English."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import partial

import pytest
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
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.evals import AudioCall
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.talkers import TalkerFactory

from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

AGENT = VoiceAgent(
    name="switching",
    languages=[Language.saudi_arabic(greeting="هلا."), Language.english(greeting="Hi.")],
    instructions="Answer briefly.",
)
RATE = 16_000
QUESTION = "Which flights go to Dubai tomorrow?"
# Told Arabic, Whisper writes each turn in Arabic, the question translated (what Whisper does).
ARABIC = {"yes": "ايوه ايوه", "question": "ما هي الرحلات الى دبي بكرة", "short": "طيب"}
# The clip's three turns: the seconds of tone, then of silence after it.
TURNS = (("yes", 1.6, 2.5), ("question", 3.2, 2.5), ("short", 0.5, 3.0))


class _Whisper:
    """Told a language, it writes the turn in it; told none, it detects English (a long "yes"
    or the question, told apart by the clip's length). It records each request's language."""

    name = "fake"
    data_flow = FAKE_FLOW

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, float]] = []

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((language, clip.seconds))
        turn = "short" if clip.seconds < 1.6 else "yes" if clip.seconds < 2.6 else "question"
        if language is None:
            text = "Yes, yes." if turn == "yes" else QUESTION
            return Transcript(text=text, language="english", billed_seconds=10.0)
        text = ARABIC[turn] if language == "ar" else "Okay."
        return Transcript(text=text, language=language, billed_seconds=10.0)

    async def aclose(self) -> None:
        return None


class _Talker:
    """One clause, in the language of the turn it answers."""

    def __init__(self) -> None:
        self.turns: list[TalkerTurn] = []

    async def reply(self, turn: TalkerTurn, *, scope: ReplyScope) -> AsyncIterator[TalkerEvent]:
        self.turns.append(turn)
        english = turn.language == "en"
        yield SpokenClause(
            text="Sure." if english else "أبشر.", language="en" if english else "ar-SA"
        )
        yield ReplyDone()


def _clip() -> AudioClip:
    pcm = b"".join(tone(on, RATE) + bytes(2 * round(off * RATE)) for _, on, off in TURNS)
    return AudioClip(pcm16=pcm, sample_rate=RATE)


def test_an_english_question_in_an_arabic_call_moves_it_and_a_long_yes_does_not(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    talker = _Talker()

    def factory(call: TalkerCall, clock: Clock) -> _Talker:
        return talker

    class _Replay(AudioCall):
        def _talkers(self) -> TalkerFactory | None:  # the test's talker, not the library's
            return factory

    stt = settings.stt.model_copy(update={"live_language": "detected"})
    whisper = _Whisper()
    replay = _Replay(
        settings=settings.model_copy(update={"stt": stt}),
        stt=whisper,
        tts=FakeTextToSpeech(seconds_per_char=0.01, languages=("ar-SA", "en")),
        agent=AGENT,
    )

    async def run() -> None:
        await replay.start()
        try:
            await replay.turn(_clip(), greeting=("هلا.",), language="ar-SA", lead_s=1.5, tail_s=2.0)
        finally:
            await replay.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=90))
    assert [(t.words, t.language) for t in talker.turns] == [
        (ARABIC["yes"], "ar"),  # a short reply heard as English moves nothing
        (QUESTION, "en"),  # the question: the detecting request's words, and the call moved
        ("Okay.", "en"),  # the short turn: sent once, in the moved language
    ]
    # Each long turn twice at once, in the call's language and naming none; the short one once.
    assert [language for language, _ in whisper.calls] == ["ar", None, "ar", None, "en"]
