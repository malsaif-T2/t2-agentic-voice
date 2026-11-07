"""Run T's replay wired to the library (first_audio_replay.py): a recording replayed through the
`evals` facade's `AudioCall` as a turn of Ole5's own talker, with a fake speech-to-text, voice and
chat model (the file-fed pipeline on the tests' tone detector and a turn analyzer that ends each
turn at its first pause, as the library's own replay tests run it); what the call gave back read
as run T reads it: the turn, whether it searched, its time from the owner's mark or from the
detector's stop, its opening, every voice request counted (the replay's greeting among them), and
the chat model's requests and tokens apart."""

from __future__ import annotations

import asyncio
from functools import partial

import pytest
from ole5_voice.agent import talker_agent
from ole5_voice.evals.first_audio_replay import CountedVoice, audio_replay, replayed
from ole5_voice.evals.first_audio_score import ReplayedCall
from ole5_voice.evals.first_audio_setup import FirstAudioParts
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.evals import ScriptedLLM, TurnReplay
from t2_agentic_voice.events import CallEnded, CallReport, ModelUsage, ToolStarted, TurnRecord
from t2_agentic_voice.events import TurnTimes as Times
from t2_agentic_voice.ports import AudioClip, Usage
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls

from tests.ole5_voice.evals.samples import WHEN
from tests.ole5_voice.evals.talker_fakes import FakeKnowledgeBase
from tests.ole5_voice.evals.timing_support import ENGLISH
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

ASKED = "how do I print a letter"


def _replay(settings: VoiceSettings, labelled: bool) -> tuple[ReplayedCall, FakeTextToSpeech]:
    chat = ScriptedLLM(
        [
            ScriptedLLM.call_tool("search_knowledge", query="print a letter"),
            ScriptedLLM.reply(
                "Open the letter, then press print.",
                usage=Usage(input_tokens=900, output_tokens=12),
            ),
        ]
    )
    tts = FakeTextToSpeech(seconds_per_char=0.03)
    replay = audio_replay(
        agent=talker_agent(FakeKnowledgeBase()),
        settings=settings,
        stt=FakeSpeechToText([ASKED]),
        tts=tts,
        llm=chat,
        phrases=None,
    )
    hold_s = settings.turns.complete_hold_ms / 1000

    async def run() -> ReplayedCall:
        await replay.start()
        try:
            return await replay.call(
                AudioClip(pcm16=tone(0.5, 16_000)),
                language="en",
                end_ms=500.0 if labelled else None,
                lead_s=0.5,
                tail_s=3.0 + hold_s,
            )
        finally:
            await replay.aclose()

    return asyncio.run(asyncio.wait_for(run(), timeout=60)), tts


@pytest.mark.parametrize("labelled", [True, False])
def test_a_recording_replays_through_the_wired_path_as_ole5s_talker_answers_it(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch, labelled: bool
) -> None:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    call, tts = _replay(settings, labelled)
    (turn,) = call.turns
    assert turn.searched and turn.failure is None and turn.ttfa_ms is not None
    (opening,) = call.openings
    assert opening is not None and 0 < opening.seconds <= 3.0
    # The chat model's two requests and their tokens apart; the voice's every request counted,
    # the replay's own greeting among them, which the call report does not count.
    assert (call.chat.requests, call.chat.input_tokens, call.chat.output_tokens) == (2, 900, 12)
    assert settings.llm.model not in {usage.model for usage in call.usage}
    english = [text for text, language in tts.calls if language == "en"]
    voice = [usage for usage in call.usage if usage.model == ENGLISH]
    assert sum(u.requests for u in voice) == len(english)  # the progress line, said at the start
    assert sum(u.characters for u in voice) == sum(map(len, english))
    assert any(text.startswith("Hi, this is the Ole5") for text in english)  # the greeting
    assert sum(u.requests for u in call.usage if u.model != settings.stt.model) == len(tts.calls)


def _times(ttfa_ms: float) -> Times:
    return Times(ttfa_ms=ttfa_ms, progress_ms=ttfa_ms - 500.0)


def test_the_time_starts_at_the_owners_mark_where_given_else_at_the_detectors_stop() -> None:
    report = CallReport(
        call_id="c",
        agent="ole5",
        started_at=WHEN,
        ended_at=WHEN,
        ended_by="hangup",
        turns=(
            TurnRecord(turn_id=0, heard="over the greeting", dropped=True),
            TurnRecord(turn_id=0, heard=ASKED, times=_times(2100.0)),
            TurnRecord(turn_id=1, heard="", times=_times(900.0)),  # nothing heard, no answer
        ),
        usage=(
            ModelUsage(
                model="openai/gpt-oss-120b", requests=2, input_tokens=5, remaining_requests=7
            ),
            ModelUsage(model=ENGLISH, requests=1, characters=20),
        ),
    )
    emitted = (
        ToolStarted(call_id="c", turn_id=0, at=WHEN, tool="search_knowledge", tool_call_id="x"),
        CallEnded(call_id="c", at=WHEN, report=report),
    )
    marked = TurnReplay(ttfa_ms=1800.0, progress_ms=1300.0)
    chat, voice = "openai/gpt-oss-120b", {ENGLISH: (2, 50)}
    by_label = replayed(marked, emitted, chat_model=chat, voice=voice, labelled=True)
    by_detector = replayed(marked, emitted, chat_model=chat, voice=voice, labelled=False)
    assert [(t.ttfa_ms, t.progress_ms, t.searched) for t in by_label.turns] == [
        (1800.0, 1300.0, True)
    ]
    assert [(t.ttfa_ms, t.progress_ms) for t in by_detector.turns] == [(2100.0, 1600.0)]
    assert by_label.chat.remaining_requests == 7 and by_label.chat.input_tokens == 5
    # The greeting's request, beyond the report's one: counted, and its characters.
    assert [(u.requests, u.characters) for u in by_label.usage] == [(1, 20), (1, 30)]


def test_the_voice_counts_each_request_by_its_languages_model() -> None:
    voice = CountedVoice(FakeTextToSpeech(), {"en": ENGLISH})

    async def say() -> None:
        async for _ in voice.synthesize("Hello there.", language="en"):
            pass

    asyncio.run(say())
    assert voice.taken() == {ENGLISH: (1, 12)} and voice.taken() == {}
    assert voice.max_chars("en") == 200 and voice.name == "fake"


def test_a_run_replays_through_the_library_by_default() -> None:
    assert FirstAudioParts().replay is audio_replay
