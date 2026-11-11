"""The parity test (the design's 9.5; plan 006, moved from plan 005): one scripted call, run as a
`TextCall` and as an `AudioCall`, takes the same path through the session: the same verdicts
(each `Interrupted`, its kind and the rule's step), the same turns (what was heard, what the
caller heard said back, whether a stop cut the reply) and the same replies (the turn each
answers, what it said, whether it played whole). So text mode tests what a real call runs.

The script: the caller speaks over the greeting, a stop word, or new words the echo says back.
The audio call runs the real file-fed pipeline with the tests' tone detector and a turn analyzer
that ends each turn at its first pause (voice/kit.py), speech-to-text the fake's (the scripted
words for each request), at real-time pace; the text call runs the same session code with no
audio, on its virtual clock. Both run the real interruption rule.

A talker's reply with a stray character takes the same path too: the same clauses said through
`TextCall` and through the audio session, the filter's in both, and `TextTurn.stray_characters`
counts what went. So does a reply that asks two questions: both say it up to its first question
(the question limit, D-085), and `TextTurn.unsaid_clauses` counts what went unsaid."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    CallEnded,
    Event,
    Interrupted,
    UserTurnEnded,
)
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.evals import AudioCall, ScriptedLLM, TextCall
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.testing.text_call_support import NoModel
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

GREETING = "Welcome to the made up support line, how can I help you today?"
SCRIPTS = {
    "stop": PRESET_WORDS["en"].stop[0],
    "new_words": "my printer keeps failing every single morning",
}


def path(events: tuple[Event, ...] | list[Event]) -> dict[str, Any]:
    """The path a call took through the session, as its public events tell it."""
    (ended,) = [e for e in events if isinstance(e, CallEnded)]
    return {
        "verdicts": [(e.turn_id, e.kind, e.reason) for e in events if isinstance(e, Interrupted)],
        "turns": [(e.turn_id, e.heard) for e in events if isinstance(e, UserTurnEnded)],
        "replies": [
            (e.turn_id, e.text, e.played_fraction == 1.0)
            for e in events
            if isinstance(e, AgentSpeechEnded)
        ],
        "records": [(t.turn_id, t.heard, t.said, t.stopped) for t in ended.report.turns],
    }


def _audio(settings: VoiceSettings, words: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    replay = AudioCall(
        settings=settings,
        stt=FakeSpeechToText([words] * 4),
        tts=FakeTextToSpeech(seconds_per_char=0.04),
    )
    hold_s = settings.turns.complete_hold_ms / 1000

    async def run() -> None:
        await replay.start()
        try:
            clip = AudioClip(pcm16=tone(0.5, 16_000))
            await replay.over_reply(
                clip, reply=(GREETING,), language="en", at_s=0.5, tail_s=3.5 + hold_s
            )
        finally:
            await replay.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=60))
    return path(replay.emitted)


def _text(settings: VoiceSettings, words: str) -> dict[str, Any]:
    agent = VoiceAgent(name="audio-call", languages=[Language.english(greeting=GREETING)])
    call = TextCall(agent, llm=NoModel(), settings=settings)

    async def run() -> None:
        async with call:
            await call.advance(0.5)  # into the greeting
            await call.user(words, during="agent_speaking")
            await call.advance(15.0)

    asyncio.run(run())
    return path(call._emitted)


# A talker's reply with a stray character and a pictograph, which the filter takes out before the
# guard, the voice and the captions read it, and what is said of it.
ASKED = "my laptop is stuck on the login screen"
STRAY = "Restart重 it now. Then sign in😀 again."
STRAY_SAID = ["Restart it now.", "Then sign in again."]


def _talker_agent() -> VoiceAgent:
    return VoiceAgent(
        name="parity-scripts",
        languages=[Language.english(greeting=GREETING)],
        instructions="Answer briefly.",
    )


# A talker's reply that asks two questions, which the question limit says up to its first.
QUESTIONS = "Is it the office laptop? Is it stuck on the login screen? Tell me more."
QUESTIONS_SAID = ["Is it the office laptop?"]


def _talker_text(settings: VoiceSettings, written: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The path of a `TextCall` whose talker writes `written` to the caller's one turn, and what
    the turn read once the call had run on: its clauses' texts and its two counts."""
    model = ScriptedLLM([ScriptedLLM.reply(written)])
    call = TextCall(_talker_agent(), llm=model, settings=settings)

    async def run() -> dict[str, Any]:
        async with call:
            asked = await call.user(ASKED)
            await call.advance(15.0)
            return {
                "clauses": [clause.text for clause in asked.clauses],
                "stray": asked.stray_characters,
                "unsaid": asked.unsaid_clauses,
            }

    turn = asyncio.run(run())
    return path(call._emitted), turn


def _talker_audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, written: str
) -> dict[str, Any]:
    """The path of an `AudioCall` whose talker writes `written` to the caller's one turn."""
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    replay = AudioCall(
        settings=settings,
        stt=FakeSpeechToText([ASKED]),
        tts=FakeTextToSpeech(seconds_per_char=0.02),
        agent=_talker_agent(),
        chat=ScriptedLLM([ScriptedLLM.reply(written)]),
    )

    async def run() -> None:
        await replay.start()
        try:
            clip = AudioClip(pcm16=tone(0.6, 16_000))
            await replay.turn(clip, greeting=(GREETING,), language="en", lead_s=0.5, tail_s=4.0)
        finally:
            await replay.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=60))
    return path(replay.emitted)


def test_a_reply_with_a_stray_character_says_the_same_clauses_as_text_and_as_audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    text, turn = _talker_text(settings, STRAY)
    assert text == _talker_audio(settings, monkeypatch, STRAY)
    assert (turn["clauses"], turn["stray"], turn["unsaid"]) == (STRAY_SAID, 2, 0)
    assert text["replies"][1] == (0, " ".join(STRAY_SAID), True)


def test_a_reply_with_two_questions_says_the_same_clauses_as_text_and_as_audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    text, turn = _talker_text(settings, QUESTIONS)
    assert text == _talker_audio(settings, monkeypatch, QUESTIONS)
    assert (turn["clauses"], turn["stray"], turn["unsaid"]) == (QUESTIONS_SAID, 0, 2)
    assert text["replies"][1] == (0, " ".join(QUESTIONS_SAID), True)


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_scripted_call_takes_the_same_path_as_text_and_as_audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, script: str
) -> None:
    words = SCRIPTS[script]
    text, audio = _text(settings, words), _audio(settings, words, monkeypatch)
    assert text == audio
    assert text["verdicts"] and text["verdicts"][0][1] == (
        "stop" if script == "stop" else "new_words"
    )
    assert text["replies"][0] == (None, GREETING, False)  # the greeting, cut
