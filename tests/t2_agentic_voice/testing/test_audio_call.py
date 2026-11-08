"""The replay of a clip over a reply (testing/audio_call.py, the design's 9.5), against a fake
`VoiceCalls` and a fake `feed_file`, so no model loads, no time passes and no request leaves:
what it builds its calls with; each clip a fresh call held in its language, greeting with the
reply as one phrase whose audio the replay's text-to-speech said, fed over it at `at_s`; its
verdict read from that call's `Interrupted` alone; the calls closed once; and what it refuses
before any call. What `replay_of` reads from a call is test_overlap_replay.py's."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import Interrupted
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.evals import AudioCall, ScriptedLLM
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice import file_transport
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.session.commands import Command, HearOverlap, StopSpeaking
from t2_agentic_voice.voice.session.session_events import AgentAudio

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.testing.feed_support import FakeFeed

CLIP = AudioClip(pcm16=tone(0.5, 16_000))
WALL = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
REPLY = ("A made-up first clause.", "And a second.")


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> FakeFeed:
    faked = FakeFeed([])
    monkeypatch.setattr(audio_call, "VoiceCalls", faked.voice_calls)
    monkeypatch.setattr(file_transport, "feed_file", faked)
    return faked


def _stopped(start: float) -> FedCall:
    frame = AgentAudio(pcm16=b"\x01\x00", sample_rate=24_000, at=start + 1.3)
    commands: tuple[tuple[float, Command], ...] = (
        (start + 0.6, HearOverlap(turn_id=0, window_ms=750)),
        (start + 1.2, StopSpeaking(reply_id=0)),
    )
    return FedCall(started_at=start, events=(frame,), commands=commands)


def _interrupted(call_id: str) -> Interrupted:
    return Interrupted(call_id=call_id, at=WALL, kind="stop", reason="stop_word")


def test_each_clip_is_a_fresh_call_over_the_reply_its_greeting(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    tts, stt = FakeTextToSpeech(seconds_per_char=0.05), FakeSpeechToText()
    feed.calls = [_stopped(10.0), FedCall(started_at=30.0, events=(), commands=())]
    feed.emits = [[_interrupted("audio-call-0"), _interrupted("audio-call-9")], []]
    replay = AudioCall(settings=settings, stt=stt, tts=tts)

    async def run() -> list[audio_call.OverlapReplay]:
        await replay.start()
        first = await replay.over_reply(
            CLIP, reply=REPLY, language="ar-SA", at_s=1.0, tail_s=4.5, word_end_ms=1000.0
        )
        second = await replay.over_reply(CLIP, reply=("Another.",), language="en", at_s=1, tail_s=2)
        await replay.aclose()
        await replay.aclose()  # a second close does nothing
        return [first, second]

    first, second = asyncio.run(run())
    assert (first.action, first.reason, first.decided_by) == ("stop", "stop_word", None)
    assert (first.last_audio_ms, first.stop_ms) == pytest.approx((1300.0, 300.0))
    assert (second.opened, second.action) == (False, None)  # another call's verdict is not its
    (calls,) = feed.built
    assert (calls.started, calls.closed) == (1, 1)
    built = calls.built
    assert (built["settings"], built["stt"], built["tts"]) == (settings, stt, tts)
    assert [asked["call_id"] for asked in feed.asked] == ["audio-call-0", "audio-call-1"]
    asked = feed.asked[0]
    assert (asked["clip"], asked["lead_s"], asked["tail_s"], asked["over_reply"]) == (
        CLIP,
        1.0,
        4.5,
        True,
    )
    assert not asked["consent"].record_audio
    language = asked["language"]
    assert (language.tag, language.greeting) == ("ar-SA", " ".join(REPLY))
    assert tts.calls == [(" ".join(REPLY), "ar-SA"), ("Another.", "en")]
    phrases = built["phrases"]  # the last reply's, said by the text-to-speech
    said = phrases.audio("Another.", language="en")
    assert len(said.pcm16) == 2 * round(len("Another.") * 0.05 * said.sample_rate)
    assert phrases.audio("Another.", language="ar").pcm16 == b""  # another language's: silence
    assert phrases.audio(language.echo_frame, language="ar-SA").pcm16 == b""


def test_its_chat_model_reaches_its_calls_for_an_uncertain_overlap(
    feed: FakeFeed, settings: VoiceSettings
) -> None:
    chat = ScriptedLLM([])
    replay = AudioCall(settings=settings, stt=FakeSpeechToText(), tts=FakeTextToSpeech(), chat=chat)

    async def run() -> None:
        await replay.start()
        await replay.aclose()

    asyncio.run(run())
    (calls,) = feed.built
    assert calls.built["chat"] is chat


def test_what_the_replay_refuses_before_any_call(feed: FakeFeed, settings: VoiceSettings) -> None:
    replay = AudioCall(settings=settings, stt=FakeSpeechToText(), tts=FakeTextToSpeech())

    async def refused() -> None:
        with pytest.raises(RuntimeError, match="start"):
            await replay.over_reply(CLIP, reply=REPLY, language="en", at_s=1.0, tail_s=4.5)
        await replay.start()
        slow = AudioClip(pcm16=tone(0.5, 8_000), sample_rate=8_000)
        with pytest.raises(ValueError, match="16000 Hz"):
            await replay.over_reply(slow, reply=REPLY, language="en", at_s=1.0, tail_s=4.5)
        with pytest.raises(ValueError, match="no phrase"):
            await replay.over_reply(CLIP, reply=(" ",), language="en", at_s=1.0, tail_s=4.5)
        replay.tts = FakeTextToSpeech(seconds_per_char=0.0)
        with pytest.raises(ValueError, match="no one rate"):
            await replay.over_reply(CLIP, reply=REPLY, language="en", at_s=1.0, tail_s=4.5)
        await replay.aclose()

    asyncio.run(refused())
    assert feed.asked == []
