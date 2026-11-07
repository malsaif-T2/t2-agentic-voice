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
    ChatTalker,
    ProgressDue,
    ReplyDone,
    ReplyScope,
    SpokenClause,
    TalkerCall,
    TalkerEvent,
)
from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.evals import AudioCall, TurnReplay
from t2_agentic_voice.languages import whisper_prompt
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.testing.text_watch import chat_talkers
from t2_agentic_voice.testing.turn_replay import OPENING_S, turn_replay_of
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClausePlayed,
    ClauseQueued,
    SessionEvent,
)
from t2_agentic_voice.voice.talkers import TalkerFactory

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.testing.text_call_support import NoModel
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

    class _Replay(AudioCall):
        def _talkers(self) -> TalkerFactory | None:  # the test's talker, not the library's
            return factory

    tts, stt = FakeTextToSpeech(seconds_per_char=0.03), FakeSpeechToText(["where is my ticket"] * 2)
    replay = _Replay(settings=settings, stt=stt, tts=tts, agent=AGENT)
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
    # The live path's Whisper prompt: an agent with no vocabulary sends the command words alone.
    assert stt.calls and {(language, prompt) for _, language, prompt in stt.calls} == {
        ("en", whisper_prompt((), "en").text)
    }
    assert ("One moment please.", "en") in tts.calls  # said once, at the start
    assert found.progress_audible_ms is not None and found.first_audible_ms is not None
    assert found.progress_audible_ms < found.first_audible_ms
    assert found.ttfa_ms == pytest.approx(found.first_audible_ms - 500.0)
    assert found.progress_ms == pytest.approx(found.progress_audible_ms - 500.0)
    assert found.times is not None and found.times.ttfa_ms is not None
    assert found.times.progress_ms is not None and found.times.progress_ms < found.times.ttfa_ms
    # The reply's opening, its own audio and never the progress line's, as sent.
    assert found.opening is not None and 0 < found.opening.seconds <= OPENING_S


def test_a_replay_of_an_instructed_agent_writes_with_the_librarys_talker_on_its_chat_model(
    settings: VoiceSettings,
) -> None:
    chat = NoModel()
    replay = AudioCall(
        settings=settings, stt=FakeSpeechToText(), tts=FakeTextToSpeech(), agent=AGENT, chat=chat
    )
    factory = replay._talkers()
    assert factory is not None
    call = TalkerCall(call_id="c-1", caller=Caller(subject="s"), language="en")
    built = factory(call, SYSTEM_CLOCK)
    assert isinstance(built, ChatTalker) and built.model is chat and built.call == call
    echo = AudioCall(settings=settings, stt=FakeSpeechToText(), tts=FakeTextToSpeech())
    assert echo._talkers() is None and chat_talkers(AGENT, settings, None) is None


def test_a_replays_opening_is_its_reply_audio_from_its_first_frame_for_three_seconds() -> None:
    """The opening is the reply's own frames as sent, its first silent frame included and the
    progress line's left out, cut at `OPENING_S`, for a listen of its first syllable."""
    rate, frame = 24_000, 480  # 20 ms frames
    quiet, loud = b"\x00\x00" * frame, b"\x00\x10" * frame
    line = AudioChunk(pcm16=loud * 10, sample_rate=rate)
    speaks = [
        Speak(reply_id=1, clause=0, turn_id=0, text="One moment.", language="en", audio=line),
        Speak(reply_id=1, clause=1, turn_id=0, text="Your ticket is open.", language="en"),
    ]
    events: list[SessionEvent] = [ClauseQueued(reply_id=1, clause=0, at=1.0, requested_at=None)]
    events += [AgentAudio(pcm16=loud, sample_rate=rate, at=1.0 + n * 0.02) for n in range(10)]
    events += [ClausePlayed(reply_id=1, clause=0, at=1.2, audio_s=0.2, chunks=1)]
    events += [ClauseQueued(reply_id=1, clause=1, at=1.5, requested_at=1.3)]
    reply = [quiet, *[loud] * 249]  # five seconds, its first frame silent
    events += [
        AgentAudio(pcm16=pcm, sample_rate=rate, at=1.5 + n * 0.02) for n, pcm in enumerate(reply)
    ]
    events += [ClausePlayed(reply_id=1, clause=1, at=6.5, audio_s=5.0, chunks=1)]
    fed = FedCall(started_at=0.5, events=tuple(events), commands=tuple((1.0, s) for s in speaks))
    found = turn_replay_of(fed, (), progress=frozenset({"One moment."}), speech_end_ms=300.0)
    assert found.opening is not None and found.opening.sample_rate == rate
    assert found.opening.seconds == pytest.approx(OPENING_S)
    assert found.opening.pcm16.startswith(quiet + loud)  # from its first frame, not the line's
    assert found.first_audible_ms == pytest.approx(1020.0) and found.ttfa_ms == pytest.approx(720.0)
    assert found.progress_audible_ms == pytest.approx(500.0)
    none = turn_replay_of(FedCall(started_at=0.0, events=(), commands=()), ())
    assert none.opening is None and none.first_audible_ms is None
